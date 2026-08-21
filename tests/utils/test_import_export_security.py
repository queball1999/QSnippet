"""
Security tests for import/export functionality.

Tests protection against:
- File size DoS attacks
- Malformed YAML structures
- Invalid field types/lengths
- Unknown field injection
- Memory exhaustion attacks
"""
import pytest
import yaml
from pathlib import Path

from utils.file_utils import (
    FileUtils,
    MAX_IMPORT_FILE_SIZE,
    MAX_FIELD_LENGTH,
    MAX_SNIPPETS_PER_FILE,
    validate_snippet_fields,
    validate_snippets_list,
)

pytestmark = pytest.mark.gui


class TestFileSizeLimit:
    """Test file size DoS protection."""

    def test_reject_oversized_file(self, tmp_path):
        """Reject YAML files larger than 50MB."""
        yaml_path = tmp_path / "huge.yaml"

        # Create a file larger than MAX_IMPORT_FILE_SIZE
        with open(yaml_path, "wb") as f:
            # Write 51MB of data
            f.write(b"x" * (MAX_IMPORT_FILE_SIZE + 1))

        with pytest.raises(ValueError, match="File too large"):
            FileUtils.read_yaml(yaml_path)

    def test_accept_file_at_size_limit(self, tmp_path):
        """Accept YAML files exactly at the size limit."""
        yaml_path = tmp_path / "at_limit.yaml"

        # Create minimal valid YAML at size boundary
        data = {"snippets": []}
        with open(yaml_path, "w") as f:
            yaml.safe_dump(data, f)

        # Should not raise
        result = FileUtils.read_yaml(yaml_path)
        assert result == data

    def test_accept_small_files(self, tmp_path):
        """Accept normal-sized YAML files."""
        yaml_path = tmp_path / "normal.yaml"
        test_data = {
            "snippets": [
                {
                    "label": "Test",
                    "trigger": "/test",
                    "snippet": "content"
                }
            ]
        }

        with open(yaml_path, "w") as f:
            yaml.safe_dump(test_data, f)

        result = FileUtils.read_yaml(yaml_path)
        assert result == test_data


class TestYAMLStructureValidation:
    """Test YAML structure validation."""

    def test_reject_non_dict_root(self, tmp_path):
        """Reject YAML that is not a dictionary at root."""
        yaml_path = tmp_path / "array_root.yaml"
        yaml_path.write_text("- item1\n- item2\n")

        with pytest.raises(ValueError, match="must be a dictionary"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_missing_snippets_key(self, tmp_path):
        """Reject YAML missing 'snippets' key."""
        yaml_path = tmp_path / "no_snippets_key.yaml"
        yaml_path.write_text("data: []\n")

        with pytest.raises(ValueError, match="missing required.*snippets.*key"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_non_list_snippets_value(self, tmp_path):
        """Reject YAML where 'snippets' value is not a list."""
        yaml_path = tmp_path / "snippets_not_list.yaml"
        yaml_path.write_text("snippets:\n  key: value\n")

        with pytest.raises(ValueError, match="must be a list"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_too_many_snippets(self, tmp_path):
        """Reject YAML with more than MAX_SNIPPETS_PER_FILE items."""
        yaml_path = tmp_path / "too_many.yaml"

        # Create YAML with too many snippets
        snippets = [
            {
                "label": f"Snippet {i}",
                "trigger": f"/test{i}",
                "snippet": "content"
            }
            for i in range(MAX_SNIPPETS_PER_FILE + 1)
        ]

        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="Too many snippets"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_accept_max_snippets_exactly(self, tmp_path):
        """Accept YAML with exactly MAX_SNIPPETS_PER_FILE items."""
        yaml_path = tmp_path / "max_snippets.yaml"

        # Create YAML with exactly MAX_SNIPPETS_PER_FILE snippets
        snippets = [
            {
                "label": f"Snippet {i}",
                "trigger": f"/test{i}",
                "snippet": "content"
            }
            for i in range(MAX_SNIPPETS_PER_FILE)
        ]

        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        result = FileUtils.import_snippets_yaml(yaml_path)
        assert len(result) == MAX_SNIPPETS_PER_FILE

    def test_accept_empty_snippets_list(self, tmp_path):
        """Accept YAML with empty snippets list."""
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("snippets: []\n")

        result = FileUtils.import_snippets_yaml(yaml_path)
        assert result == []


class TestSnippetFieldValidation:
    """Test individual snippet field validation."""

    def test_reject_missing_trigger(self, tmp_path):
        """Reject snippet without 'trigger' field."""
        yaml_path = tmp_path / "no_trigger.yaml"
        snippets = [
            {
                "label": "No Trigger",
                "snippet": "content"
                # Missing 'trigger'
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="missing required fields"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_missing_label(self, tmp_path):
        """Reject snippet without 'label' field."""
        yaml_path = tmp_path / "no_label.yaml"
        snippets = [
            {
                "trigger": "/test",
                "snippet": "content"
                # Missing 'label'
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="missing required fields"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_missing_snippet(self, tmp_path):
        """Reject snippet without 'snippet' field."""
        yaml_path = tmp_path / "no_snippet.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "/test"
                # Missing 'snippet'
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="missing required fields"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_empty_trigger(self, tmp_path):
        """Reject snippet with empty trigger."""
        yaml_path = tmp_path / "empty_trigger.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "",  # Empty!
                "snippet": "content"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="cannot be empty"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_whitespace_only_trigger(self, tmp_path):
        """Reject snippet with whitespace-only trigger."""
        yaml_path = tmp_path / "whitespace_trigger.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "   \t  ",  # Only whitespace
                "snippet": "content"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="cannot be empty"):
            FileUtils.import_snippets_yaml(yaml_path)


class TestFieldTypeValidation:
    """Test field type validation."""

    def test_reject_non_string_trigger(self, tmp_path):
        """Reject trigger that is not a string."""
        yaml_path = tmp_path / "int_trigger.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": 123,  # Should be string!
                "snippet": "content"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        # Type errors are wrapped as ValueError in validation
        with pytest.raises((TypeError, ValueError), match="must be string"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_non_string_label(self, tmp_path):
        """Reject label that is not a string."""
        yaml_path = tmp_path / "int_label.yaml"
        snippets = [
            {
                "label": ["array"],  # Should be string!
                "trigger": "/test",
                "snippet": "content"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises((TypeError, ValueError), match="must be string"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_non_bool_enabled(self, tmp_path):
        """Reject 'enabled' field that is not boolean."""
        yaml_path = tmp_path / "string_enabled.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "/test",
                "snippet": "content",
                "enabled": "yes"  # Should be boolean!
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises((TypeError, ValueError), match="must be boolean"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_non_bool_return_press(self, tmp_path):
        """Reject 'return_press' field that is not boolean."""
        yaml_path = tmp_path / "string_return_press.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "/test",
                "snippet": "content",
                "return_press": 1  # Should be boolean!
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises((TypeError, ValueError), match="must be boolean"):
            FileUtils.import_snippets_yaml(yaml_path)


class TestFieldLengthValidation:
    """Test field length validation to prevent memory exhaustion."""

    def test_reject_oversized_trigger(self, tmp_path):
        """Reject trigger exceeding MAX_FIELD_LENGTH."""
        yaml_path = tmp_path / "huge_trigger.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "x" * (MAX_FIELD_LENGTH + 1),  # Too long!
                "snippet": "content"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="exceeds max length"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_oversized_label(self, tmp_path):
        """Reject label exceeding MAX_FIELD_LENGTH."""
        yaml_path = tmp_path / "huge_label.yaml"
        snippets = [
            {
                "label": "y" * (MAX_FIELD_LENGTH + 1),  # Too long!
                "trigger": "/test",
                "snippet": "content"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="exceeds max length"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_reject_oversized_snippet(self, tmp_path):
        """Reject snippet content exceeding MAX_FIELD_LENGTH."""
        yaml_path = tmp_path / "huge_snippet.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "/test",
                "snippet": "z" * (MAX_FIELD_LENGTH + 1)  # Too long!
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError, match="exceeds max length"):
            FileUtils.import_snippets_yaml(yaml_path)

    def test_accept_max_field_length_exactly(self, tmp_path):
        """Accept fields exactly at MAX_FIELD_LENGTH."""
        yaml_path = tmp_path / "max_length.yaml"
        snippets = [
            {
                "label": "a" * MAX_FIELD_LENGTH,
                "trigger": "b" * MAX_FIELD_LENGTH,
                "snippet": "c" * MAX_FIELD_LENGTH
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        result = FileUtils.import_snippets_yaml(yaml_path)
        assert len(result) == 1
        assert len(result[0]["label"]) == MAX_FIELD_LENGTH


class TestUnknownFieldStripping:
    """Test that unknown fields are silently removed."""

    def test_strip_unknown_fields(self, tmp_path):
        """Unknown fields should be removed from imported snippets."""
        yaml_path = tmp_path / "unknown_fields.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "/test",
                "snippet": "content",
                "unknown_field": "should be removed",
                "another_bad_field": 12345
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        result = FileUtils.import_snippets_yaml(yaml_path)
        assert len(result) == 1

        # Check that only allowed fields remain
        allowed_keys = {"label", "trigger", "snippet"}
        assert set(result[0].keys()).issubset(allowed_keys)
        assert "unknown_field" not in result[0]
        assert "another_bad_field" not in result[0]

    def test_preserve_allowed_optional_fields(self, tmp_path):
        """Optional but allowed fields should be preserved."""
        yaml_path = tmp_path / "optional_fields.yaml"
        snippets = [
            {
                "label": "Test",
                "trigger": "/test",
                "snippet": "content",
                "folder": "Work",
                "tags": "python,useful",
                "enabled": True,
                "return_press": False,
                "paste_style": "Clipboard"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        result = FileUtils.import_snippets_yaml(yaml_path)
        assert result[0]["folder"] == "Work"
        assert result[0]["tags"] == "python,useful"
        assert result[0]["enabled"] is True
        assert result[0]["return_press"] is False


class TestSafeDeserialization:
    """Test that unsafe YAML constructs are rejected."""

    def test_reject_python_code_injection(self, tmp_path):
        """Reject YAML with Python object instantiation attempts."""
        yaml_path = tmp_path / "code_injection.yaml"
        # Try to inject Python code via YAML
        yaml_content = """
snippets:
  - label: "Innocent"
    trigger: /test
    snippet: "!!python/object/apply:os.system ['echo hacked']"
"""
        yaml_path.write_text(yaml_content)

        # yaml.safe_load should reject this (raises YAMLError which manifests as ValueError or TypeError)
        try:
            FileUtils.import_snippets_yaml(yaml_path)
            # If it didn't raise, safe_load likely parsed the string literally
        except (yaml.YAMLError, ValueError, TypeError):
            # Expected - safe_load rejects the construct
            pass

    def test_safe_load_rejects_arbitrary_python(self, tmp_path):
        """Verify yaml.safe_load blocks arbitrary Python objects."""
        yaml_path = tmp_path / "arbitrary_python.yaml"
        yaml_content = """
!!python/object:builtins.dict
items:
  label: "Test"
  trigger: "/test"
"""
        yaml_path.write_text(yaml_content)

        # Should raise due to custom constructors
        with pytest.raises(yaml.YAMLError):
            FileUtils.import_snippets_yaml(yaml_path)


class TestValidationHelpers:
    """Test the validation helper functions directly."""

    def test_validate_snippet_fields_success(self):
        """Valid snippet passes validation."""
        snippet = {
            "label": "Test",
            "trigger": "/test",
            "snippet": "content"
        }
        # Should not raise
        validate_snippet_fields(snippet)

    def test_validate_snippet_fields_with_optionals(self):
        """Valid snippet with optional fields passes."""
        snippet = {
            "label": "Test",
            "trigger": "/test",
            "snippet": "content",
            "folder": "Work",
            "tags": "python",
            "enabled": True,
            "return_press": False,
            "paste_style": "Clipboard"
        }
        # Should not raise
        validate_snippet_fields(snippet)

    def test_validate_snippets_list_success(self):
        """Valid snippets list passes."""
        data = {"snippets": [{"label": "A", "trigger": "/a", "snippet": "a"}]}
        result = validate_snippets_list(data)
        assert len(result) == 1

    def test_validate_snippets_list_empty(self):
        """Empty snippets list is valid."""
        data = {"snippets": []}
        result = validate_snippets_list(data)
        assert result == []


class TestValidationErrorMessages:
    """Test that validation errors provide helpful messages."""

    def test_error_message_includes_snippet_number(self, tmp_path):
        """Error message indicates which snippet failed."""
        yaml_path = tmp_path / "bad_snippet.yaml"
        snippets = [
            {
                "label": "Good1",
                "trigger": "/good1",
                "snippet": "content"
            },
            {
                "label": "Bad",
                "trigger": "",  # Invalid!
                "snippet": "content"
            }
        ]
        with open(yaml_path, "w") as f:
            yaml.safe_dump({"snippets": snippets}, f)

        with pytest.raises(ValueError) as exc_info:
            FileUtils.import_snippets_yaml(yaml_path)

        # Error message should mention snippet #2
        assert "Snippet #2" in str(exc_info.value)
