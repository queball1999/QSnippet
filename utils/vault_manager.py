"""AES-256-GCM vault manager for QSnippet.

Architecture
------------
The AES-256 key lives **only in memory** as a mutable ``bytearray`` so it can
be zeroed on lock.  It is never written to disk.  Vault crypto material (salt,
HMAC verifier, optional recovery key blob) is stored in the user's
``config.yaml`` and passed in by the caller on every operation.

Auto-lock is implemented with a :class:`threading.Timer` daemon thread.  The
timer fires :meth:`VaultManager.lock` which zeros ``self.key`` and invokes
``lock_callback``.

**Thread-safety note:** ``lock_callback`` fires from the timer thread, not the
Qt main thread - callers must dispatch any UI work via
:func:`~PySide6.QtCore.QTimer.singleShot` or equivalent (see
:meth:`set_lock_callback`).

**Timer-race protection:** All bulk re-encryption operations cancel the
auto-lock timer before starting work and restart it only on success.  This
prevents the timer from zeroing ``self.key`` while snippets are being
re-encrypted.

Singleton
---------
Use :meth:`VaultManager.get_instance` for the application-wide instance.
"""

import os
import hmac
import hashlib
import base64
import logging
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class VaultError(Exception):
    """Raised when a vault operation cannot proceed (e.g. vault is locked)."""


class VaultManager:
    """Singleton that manages AES-256-GCM vault encryption state.

    The in-memory key is stored as a mutable ``bytearray`` so it can be
    explicitly zeroed on lock.  All config persistence is the caller's
    responsibility - this class only reads config to verify credentials and
    returns updated config dicts for the caller to save.

    Attributes:
        instance: Application-wide singleton instance.
        class_lock: Lock guarding singleton creation.
    """

    instance: Optional['VaultManager'] = None
    class_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'VaultManager':
        """Return the application-wide singleton, creating it on first call.

        Returns:
            VaultManager: The singleton instance.
        """
        if cls.instance is None:
            with cls.class_lock:
                if cls.instance is None:
                    cls.instance = VaultManager()
        return cls.instance

    def __init__(self) -> None:
        self.key: Optional[bytearray] = None
        self.timer: Optional[threading.Timer] = None
        self.auto_lock_seconds: int = 15 * 60
        self.lock_callback: Optional[Callable] = None
        self._failed_unlock_attempts: int = 0
        self._aad_migration_done: bool = False

    # --State

    def is_setup(self, config: dict) -> bool:
        """Return ``True`` if the vault has been configured (salt + verifier present).

        Args:
            config: Application config dict containing a ``vault`` sub-dict.

        Returns:
            bool: ``True`` when vault crypto material exists in *config*.
        """
        v = config.get("vault", {})
        return bool(v.get("salt") and v.get("verifier"))

    def is_unlocked(self) -> bool:
        """Return ``True`` if the vault key is currently held in memory.

        Returns:
            bool: ``True`` when the vault is unlocked.
        """
        return self.key is not None

    # Password operations

    def setup(self, password: str, config: dict, recovery_code: str = None) -> dict:
        """Perform first-time vault setup: derive key, store salt and verifier.

        Args:
            password: Master vault password chosen by the user.
            config: Current application config dict.
            recovery_code: Optional recovery code string.  When provided,
                recovery key material (salt, verifier, wrapped key blob) is
                stored in the returned config.

        Returns:
            dict: Updated application config dict with ``vault`` sub-dict
            populated.  The vault is left in the unlocked state.
        """
        if len(password) > 255:
            raise VaultError("Password exceeds maximum length of 255 characters.")
        salt = os.urandom(32)
        key = self.derive_key(password, salt)
        verifier = self.make_verifier(key)

        existing_vault = config.get("vault", {})
        vault_cfg: dict = {
            "salt": base64.b64encode(salt).decode(),
            "verifier": base64.b64encode(verifier).decode(),
            "unlock_on_launch": existing_vault.get("unlock_on_launch", False),
            "auto_lock_minutes": existing_vault.get("auto_lock_minutes", 15),
        }
        if recovery_code:
            rec_salt = os.urandom(32)
            rec_key = self.derive_key(recovery_code, rec_salt)
            try:
                vault_cfg["rec_salt"] = base64.b64encode(rec_salt).decode()
                vault_cfg["rec_verifier"] = base64.b64encode(self.make_verifier(rec_key)).decode()
                vault_cfg["rec_key_blob"] = base64.b64encode(self.wrap_key(key, rec_key)).decode()
            finally:
                for i in range(len(rec_key)):
                    rec_key[i] = 0

        config = dict(config)
        config["vault"] = vault_cfg
        self.key = key
        self.reset_timer()
        logger.info("Vault setup complete")
        return config

    def unlock(self, password: str, config: dict) -> bool:
        """Attempt to unlock the vault with a password.

        Args:
            password: The master vault password to verify.
            config: Application config dict containing vault crypto material.

        Returns:
            bool: ``True`` on successful unlock, ``False`` on incorrect password
            or missing/malformed config.
        """
        if len(password) > 255:
            return False
        v = config.get("vault", {})
        try:
            salt = base64.b64decode(v["salt"])
            stored = base64.b64decode(v["verifier"])
        except (KeyError, Exception):
            return False

        key = self.derive_key(password, salt)
        if hmac.compare_digest(self.make_verifier(key), stored):
            self._failed_unlock_attempts = 0
            self.key = key
            self.reset_timer()
            logger.info("Vault unlocked")
            return True

        for i in range(len(key)):
            key[i] = 0
        self._failed_unlock_attempts += 1
        delay = min(2 ** max(0, self._failed_unlock_attempts - 5), 60)
        if delay > 0:
            import time
            time.sleep(delay)
        logger.warning("Vault unlock failed: incorrect password (attempt %d)", self._failed_unlock_attempts)
        return False

    def lock(self) -> None:
        """Zero the key and clear it from memory, then cancel the auto-lock timer.

        Safe to call when already locked.  ``lock_callback`` (if set) is
        invoked after the key is cleared.  The callback fires from the timer
        daemon thread - any Qt UI work inside it must be dispatched to the
        main thread.

        Returns:
            None
        """
        if self.key is not None:
            for i in range(len(self.key)):
                self.key[i] = 0
        self.key = None
        self._aad_migration_done = False
        if self.timer:
            self.timer.cancel()
            self.timer = None
        logger.info("Vault locked")
        if self.lock_callback:
            try:
                self.lock_callback()
            except Exception:
                pass

    def change_password(self, old_pwd: str, new_pwd: str, config: dict, db,
                        use_recovery: bool = False) -> tuple:
        """Re-encrypt all vault snippets under a new password.

        The auto-lock timer is suspended for the duration of the operation to
        prevent the timer thread from zeroing ``self.key`` mid-encrypt.  The
        timer is restarted only after the DB transaction commits successfully.

        All snippet writes are performed in a single atomic DB transaction.
        ``self.key`` is only updated after the transaction commits.  Recovery
        material is **not** carried over (the old blob wrapped the old key).

        Args:
            old_pwd: Current vault password (or recovery code when
                *use_recovery* is ``True``).
            new_pwd: New vault password to set.
            config: Application config dict.
            db: :class:`~utils.snippet_db.SnippetDB` instance.
            use_recovery: When ``True``, authenticate with a recovery code
                instead of the current password.

        Returns:
            tuple[bool, dict]: ``(True, updated_config)`` on success or
            ``(False, original_config)`` on authentication or DB failure.
        """
        if use_recovery:
            if not self.unlock_with_recovery_code(old_pwd, config):
                return False, config
        elif not self.unlock(old_pwd, config):
            return False, config

        # Suspend auto-lock for the duration of the re-encryption so the
        # background timer cannot zero self.key mid-operation.
        self.pause_timer()

        salt = os.urandom(32)
        new_key = self.derive_key(new_pwd, salt)

        try:
            self.reencrypt_all_snippets(new_key, db)
        except Exception as exc:
            logger.error("Re-encryption failed during password change: %s", exc)
            self.resume_timer()
            return False, config

        config = dict(config)
        existing_vault = config.get("vault", {})
        config["vault"] = {
            "salt": base64.b64encode(salt).decode(),
            "verifier": base64.b64encode(self.make_verifier(new_key)).decode(),
            "unlock_on_launch": existing_vault.get("unlock_on_launch", False),
            "auto_lock_minutes": existing_vault.get("auto_lock_minutes", 15),
            # Recovery material is not carried over - old blob wrapped the old key.
        }
        self.reset_timer()
        logger.info("Vault password changed")
        return True, config

    def force_change_password_authenticated(self, new_pwd: str, recovery_code: str,
                                            config: dict, db) -> tuple:
        """Re-key an already-unlocked vault and cycle the recovery code.

        Called after a recovery-code unlock to force the user to set a new
        password and generate fresh recovery material.  Vault must already be
        unlocked (``self.key`` must be set).

        The auto-lock timer is suspended for the duration of the operation.

        Args:
            new_pwd: New vault password.
            recovery_code: New recovery code to store (replaces the old one).
            config: Application config dict.
            db: :class:`~utils.snippet_db.SnippetDB` instance.

        Returns:
            tuple[bool, dict]: ``(True, updated_config)`` on success or
            ``(False, original_config)`` on failure.
        """
        if not self.key:
            logger.error("force_change_password_authenticated: vault is locked")
            return False, config

        self.pause_timer()

        salt = os.urandom(32)
        new_key = self.derive_key(new_pwd, salt)

        try:
            self.reencrypt_all_snippets(new_key, db)
        except Exception as exc:
            logger.error("Re-encryption failed during force password reset: %s", exc)
            self.resume_timer()
            return False, config

        rec_salt = os.urandom(32)
        rec_key = self.derive_key(recovery_code, rec_salt)
        try:
            config = dict(config)
            existing_vault = config.get("vault", {})
            config["vault"] = {
                "salt": base64.b64encode(salt).decode(),
                "verifier": base64.b64encode(self.make_verifier(new_key)).decode(),
                "rec_salt": base64.b64encode(rec_salt).decode(),
                "rec_verifier": base64.b64encode(self.make_verifier(rec_key)).decode(),
                "rec_key_blob": base64.b64encode(self.wrap_key(new_key, rec_key)).decode(),
                "unlock_on_launch": existing_vault.get("unlock_on_launch", False),
                "auto_lock_minutes": existing_vault.get("auto_lock_minutes", 15),
            }
        finally:
            for i in range(len(rec_key)):
                rec_key[i] = 0

        self.reset_timer()
        logger.info("Vault password force-reset after recovery")
        return True, config

    def disable_vault(self, password: str, config: dict, db, target_folder: str = "",
                      use_recovery: bool = False, delete_data: bool = False) -> tuple:
        """Disable the vault, either deleting or decrypting its encrypted contents.

        The auto-lock timer is suspended for the duration of the operation.
        Individual failures are logged but do not abort the operation
        (remaining snippets/placeholders are still processed).

        Args:
            password: Vault password (or recovery code when *use_recovery* is
                ``True``) used to authenticate before decrypting.
            config: Application config dict.
            db: :class:`~utils.snippet_db.SnippetDB` instance.
            target_folder: Destination folder for decrypted snippets. Ignored
                when *delete_data* is ``True``.
            use_recovery: When ``True``, authenticate with a recovery code.
            delete_data: When ``True``, permanently delete every encrypted
                snippet and custom placeholder instead of decrypting them.

        Returns:
            tuple[bool, dict]: ``(True, updated_config)`` on success or
            ``(False, original_config)`` on authentication failure.
        """
        if use_recovery:
            if not self.unlock_with_recovery_code(password, config):
                return False, config
        elif not self.unlock(password, config):
            return False, config

        self.pause_timer()

        if delete_data:
            for s in db.get_vault_snippets():
                try:
                    db.delete_snippet(s["id"])
                except Exception as exc:
                    logger.error(
                        "Failed to delete vault snippet %s: %s", s.get("id"), exc
                    )
            for p in db.get_all_custom_placeholders():
                if not p.get("is_encrypted"):
                    continue
                try:
                    db.delete_custom_placeholder(p["id"])
                except Exception as exc:
                    logger.error(
                        "Failed to delete vault placeholder %s: %s", p.get("id"), exc
                    )
        else:
            for s in db.get_vault_snippets():
                try:
                    aad = (s.get("vault_uuid") or "").encode()
                    plain = self.decrypt(s["snippet"], aad=aad)
                    db.update_snippet_content(s["id"], plain)
                    db.update_snippet_folder(s["id"], target_folder)
                    db.set_snippet_encrypted(s["id"], False)
                    db.set_snippet_vault_uuid(s["id"], None)
                except Exception as exc:
                    logger.error(
                        "Decrypt failed for snippet %s during vault disable: %s",
                        s.get("id"), exc,
                    )
            for p in db.get_all_custom_placeholders():
                if not p.get("is_encrypted"):
                    continue
                try:
                    aad = (p.get("vault_uuid") or "").encode()
                    plain = self.decrypt(p["value"], aad=aad)
                    db.update_custom_placeholder({
                        "id": p["id"],
                        "name": p["name"],
                        "value": plain,
                        "description": p.get("description", ""),
                        "is_encrypted": 0,
                        "vault_uuid": None,
                    })
                except Exception as exc:
                    logger.error(
                        "Decrypt failed for placeholder %s during vault disable: %s",
                        p.get("id"), exc,
                    )

        db.clear_vault_folders()

        config = dict(config)
        existing_vault = config.get("vault", {})
        config["vault"] = {
            "salt": "",
            "verifier": "",
            "unlock_on_launch": existing_vault.get("unlock_on_launch", False),
            "auto_lock_minutes": existing_vault.get("auto_lock_minutes", 15),
        }
        self.lock()
        if delete_data:
            logger.info("Vault disabled; encrypted data deleted")
        else:
            logger.info("Vault disabled; snippets moved to '%s'", target_folder)
        return True, config

    # Encrypt/Decrypt

    def encrypt(self, plaintext: str, aad: bytes = b"") -> str:
        """AES-256-GCM encrypt a plaintext string.

        Args:
            plaintext: UTF-8 string to encrypt.
            aad: Optional additional authenticated data bound to this ciphertext.
                Pass the snippet's ``vault_uuid`` encoded as bytes to cryptographically
                bind the blob to its row; an attacker swapping blobs between rows will
                cause decryption to fail. Defaults to ``b""`` (no binding) for
                backward compatibility with pre-AAD blobs.

        Returns:
            str: Base64-encoded ``nonce (12 B) + ciphertext + GCM tag``.

        Raises:
            VaultError: If the vault is locked (``self.key`` is ``None``).
        """
        if not self.key:
            raise VaultError("Vault is locked")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        ct = AESGCM(bytes(self.key)).encrypt(nonce, plaintext.encode("utf-8"), aad or None)
        return base64.b64encode(nonce + ct).decode("utf-8")

    def decrypt(self, blob: str, aad: bytes = b"") -> str:
        """AES-256-GCM decrypt a ciphertext blob produced by :meth:`encrypt`.

        Args:
            blob: Base64-encoded string as returned by :meth:`encrypt`.
            aad: Additional authenticated data that was passed at encryption time.
                Must match exactly or decryption will raise an authentication error.
                Defaults to ``b""`` for backward compatibility with pre-AAD blobs.

        Returns:
            str: Decrypted UTF-8 plaintext.

        Raises:
            VaultError: If the vault is locked (``self.key`` is ``None``).
            Exception: If authentication fails (tampered ciphertext, wrong AAD) or the
                blob is malformed.
        """
        if not self.key:
            raise VaultError("Vault is locked")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        data = base64.b64decode(blob.encode("utf-8"))
        nonce, ct = data[:12], data[12:]
        return AESGCM(bytes(self.key)).decrypt(nonce, ct, aad or None).decode("utf-8")

    # Auto-lock

    def set_auto_lock_minutes(self, minutes: int) -> None:
        """Set the inactivity timeout before the vault auto-locks.

        Args:
            minutes: Timeout in minutes.  ``0`` disables auto-lock.

        Returns:
            None
        """
        self.auto_lock_seconds = max(0, minutes) * 60
        if self.key:
            self.reset_timer()

    def set_lock_callback(self, callback: Callable) -> None:
        """Register a callback to be invoked when the vault auto-locks.

        The callback is called from the :class:`threading.Timer` daemon thread,
        **not** the Qt main thread.  Any UI manipulation inside *callback* must
        be dispatched to the main thread (e.g. via ``QTimer.singleShot(0, fn)``).

        Args:
            callback: Zero-argument callable invoked after :meth:`lock` clears
                the key.

        Returns:
            None
        """
        self.lock_callback = callback

    def reset_activity_timer(self) -> None:
        """Reset the inactivity timer on any vault interaction.

        Has no effect when the vault is locked.

        Returns:
            None
        """
        if self.key:
            self.reset_timer()

    # Private

    def reset_timer(self) -> None:
        """(Re-)start the auto-lock countdown timer.

        Cancels any running timer before starting a new one.  Does not start
        a timer when ``auto_lock_seconds`` is ``0`` (disabled).
        """
        if self.timer:
            self.timer.cancel()
        if self.auto_lock_seconds > 0:
            self.timer = threading.Timer(self.auto_lock_seconds, self.lock)
            self.timer.daemon = True
            self.timer.start()

    def pause_timer(self) -> None:
        """Cancel the auto-lock timer without locking the vault.

        Call this at the start of any long-running vault operation to prevent
        the timer from zeroing ``self.key`` mid-operation.  Always pair with
        :meth:`resume_timer` or :meth:`reset_timer` in the success path and
        a matching call in all failure/exception paths.
        """
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def resume_timer(self) -> None:
        """Restart the auto-lock timer after an operation completes or fails.

        This is the counterpart to :meth:`pause_timer` for failure paths that
        should leave the vault unlocked (e.g. failed password change).
        """
        if self.key:
            self.reset_timer()

    def reencrypt_all_snippets(self, new_key: bytearray, db) -> None:
        """Decrypt all vault snippets with the current key and re-encrypt under *new_key*.

        Pre-encrypts all blobs in memory before writing to the database so that
        the DB write is a single atomic operation.  ``self.key`` is updated to
        *new_key* only after the DB transaction commits.  The old key is zeroed
        after a successful commit.

        Args:
            new_key: New AES-256 key bytearray to encrypt snippets under.
            db: :class:`~utils.snippet_db.SnippetDB` instance.

        Returns:
            None

        Raises:
            VaultError: If the vault is locked when :meth:`decrypt` is called.
            Exception: Propagates any decryption, encryption, or DB error;
                ``self.key`` is restored to its original value on failure.
        """
        vault_snippets = db.get_vault_snippets()

        decrypted: list = []
        for s in vault_snippets:
            aad = (s.get("vault_uuid") or "").encode()
            plain = self.decrypt(s["snippet"], aad=aad)
            decrypted.append((s["id"], plain, aad))

        old_key = bytearray(self.key)
        self.key = new_key
        try:
            updates = [(sid, self.encrypt(plain, aad=aad)) for sid, plain, aad in decrypted]
        except Exception:
            self.key = old_key
            raise

        try:
            db.bulk_update_snippet_content(updates)
        except Exception:
            self.key = old_key
            raise

        for i in range(len(old_key)):
            old_key[i] = 0

        logger.info("Re-encrypted %d vault snippets", len(decrypted))

    def migrate_existing_vault_snippets_aad(self, db) -> None:
        """Assign a ``vault_uuid`` to encrypted snippets/placeholders that predate AAD binding.

        Legacy blobs (encrypted before AAD support was added) decrypt with no
        AAD. This one-time pass re-encrypts each such blob under a freshly
        generated UUID, which is then bound as AES-GCM additional authenticated
        data. Safe to call repeatedly; rows that already have a ``vault_uuid``
        are skipped. No-op if the vault is locked.
        """
        if not self.is_unlocked():
            return
        import uuid as _uuid

        for s in db.get_vault_snippets():
            if s.get("vault_uuid"):
                continue
            try:
                plain = self.decrypt(s["snippet"], aad=b"")
                new_uuid = str(_uuid.uuid4())
                new_blob = self.encrypt(plain, aad=new_uuid.encode())
                db.update_snippet_vault_uuid(s["id"], new_blob, new_uuid)
            except Exception:
                logger.warning("AAD migration skipped for snippet id=%s", s.get("id"))

        for ph in db.get_vault_placeholders():
            if ph.get("vault_uuid"):
                continue
            try:
                plain = self.decrypt(ph["value"], aad=b"")
                new_uuid = str(_uuid.uuid4())
                new_blob = self.encrypt(plain, aad=new_uuid.encode())
                db.update_placeholder_vault_uuid(ph["id"], new_blob, new_uuid)
            except Exception:
                logger.warning("AAD migration skipped for placeholder id=%s", ph.get("id"))

        self._aad_migration_done = True
        logger.info("AAD migration pass complete")

    @staticmethod
    def derive_key(password: str, salt: bytes) -> bytearray:
        """Derive a 32-byte AES key from *password* using PBKDF2-HMAC-SHA256.

        Uses 600 000 iterations per NIST SP 800-132 (2024 guidance).

        Args:
            password: User-supplied password string.
            salt: 32-byte random salt.

        Returns:
            bytearray: 32-byte derived key as a mutable bytearray (zeroable).
        """
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000,
            backend=default_backend(),
        )
        return bytearray(kdf.derive(password.encode("utf-8")))

    @staticmethod
    def make_verifier(key: bytearray) -> bytes:
        """Produce a fixed-purpose HMAC used to verify the key without exposing it.

        Args:
            key: AES-256 key bytearray.

        Returns:
            bytes: 32-byte HMAC-SHA256 digest over a fixed label string.
        """
        return hmac.new(bytes(key), b"qsnippet-vault-verify", hashlib.sha256).digest()

    def has_recovery(self, config: dict) -> bool:
        """Return ``True`` if recovery key material is present in *config*.

        Args:
            config: Application config dict.

        Returns:
            bool: ``True`` when ``rec_salt``, ``rec_verifier``, and
            ``rec_key_blob`` are all present in the ``vault`` sub-dict.
        """
        v = config.get("vault", {})
        return bool(v.get("rec_salt") and v.get("rec_verifier") and v.get("rec_key_blob"))

    def unlock_with_recovery_code(self, code: str, config: dict) -> bool:
        """Attempt to unlock the vault using the recovery code.

        Args:
            code: Recovery code string (format ``xxxx-xxxx-xxxx-xxxx-xxxx``).
            config: Application config dict containing recovery key material.

        Returns:
            bool: ``True`` on successful unlock, ``False`` otherwise.
        """
        v = config.get("vault", {})
        try:
            rec_salt = base64.b64decode(v["rec_salt"])
            stored_verifier = base64.b64decode(v["rec_verifier"])
            key_blob = base64.b64decode(v["rec_key_blob"])
        except (KeyError, Exception):
            return False

        rec_key = self.derive_key(code, rec_salt)
        try:
            if not hmac.compare_digest(self.make_verifier(rec_key), stored_verifier):
                self._failed_unlock_attempts += 1
                delay = min(2 ** max(0, self._failed_unlock_attempts - 5), 60)
                if delay > 0:
                    import time
                    time.sleep(delay)
                logger.warning("Vault recovery failed: incorrect recovery code (attempt %d)", self._failed_unlock_attempts)
                return False

            vault_key = self.unwrap_key(key_blob, rec_key)
            if vault_key is None:
                return False
        finally:
            for i in range(len(rec_key)):
                rec_key[i] = 0

        self._failed_unlock_attempts = 0
        self.key = vault_key
        self.reset_timer()
        logger.info("Vault unlocked via recovery code")
        return True

    @staticmethod
    def wrap_key(vault_key: bytearray, wrapping_key: bytearray) -> bytes:
        """AES-GCM-wrap *vault_key* under *wrapping_key*.

        Args:
            vault_key: 32-byte vault key to wrap.
            wrapping_key: 32-byte key-encryption key.

        Returns:
            bytes: ``nonce (12 B) + AES-GCM ciphertext`` of *vault_key*.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        return nonce + AESGCM(bytes(wrapping_key)).encrypt(nonce, bytes(vault_key), None)

    @staticmethod
    def unwrap_key(blob: bytes, wrapping_key: bytearray) -> Optional[bytearray]:
        """Unwrap a key blob produced by :meth:`wrap_key`.

        Args:
            blob: ``nonce + ciphertext`` bytes as returned by :meth:`wrap_key`.
            wrapping_key: 32-byte key-encryption key.

        Returns:
            bytearray: Unwrapped vault key, or ``None`` on authentication failure.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            nonce, ct = blob[:12], blob[12:]
            return bytearray(AESGCM(bytes(wrapping_key)).decrypt(nonce, ct, None))
        except Exception:
            return None

    # Export file encryption

    @staticmethod
    def encrypt_export(data: bytes, password: str) -> dict:
        """Encrypt raw bytes for a portable, self-contained export bundle.

        Generates a fresh random salt and derives a 32-byte AES-256 key using
        the same PBKDF2-HMAC-SHA256 parameters as the vault.  The resulting
        dict is stored as the top-level structure of an encrypted export file.

        The export key is independent of the vault's in-memory key so the file
        can be decrypted on any machine where the user knows their password.

        Args:
            data: Raw bytes to encrypt (e.g. UTF-8 serialised YAML).
            password: Password string to derive the encryption key from.

        Returns:
            dict: Header with ``kdf_salt`` (base64 str), ``kdf_iterations``
                (int), and ``data`` (base64 str of nonce + ciphertext + GCM tag).
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        salt = os.urandom(32)
        key = VaultManager.derive_key(password, salt)
        try:
            nonce = os.urandom(12)
            ct = AESGCM(bytes(key)).encrypt(nonce, data, None)
            return {
                "kdf_salt": base64.b64encode(salt).decode(),
                "kdf_iterations": 600_000,
                "data": base64.b64encode(nonce + ct).decode(),
            }
        finally:
            for i in range(len(key)):
                key[i] = 0

    @staticmethod
    def decrypt_export(header: dict, password: str) -> bytes:
        """Decrypt a self-contained export bundle produced by :meth:`encrypt_export`.

        Args:
            header: Dict from the export file containing ``kdf_salt``,
                ``kdf_iterations``, and ``data``.
            password: Password string used at encryption time.

        Returns:
            bytes: Decrypted raw bytes.

        Raises:
            ValueError: If *header* is missing required keys.
            Exception: If GCM authentication fails (wrong password or tampered
                ciphertext).
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            salt = base64.b64decode(header["kdf_salt"])
        except (KeyError, Exception) as exc:
            raise ValueError(f"Malformed export header: {exc}") from exc
        key = VaultManager.derive_key(password, salt)
        try:
            raw = base64.b64decode(header["data"])
            nonce, ct = raw[:12], raw[12:]
            return AESGCM(bytes(key)).decrypt(nonce, ct, None)
        finally:
            for i in range(len(key)):
                key[i] = 0
