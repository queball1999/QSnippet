from .config_utils import *
from .file_utils import *
from .keyboard_utils import *
from .logging_utils import *
from .snippet_db import SnippetDB

import platform
if platform.system() == "Windows":
    from .reg_utils import *