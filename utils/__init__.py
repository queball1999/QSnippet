from .config_utils import *
from .file_utils import *
from .keyboard_utils import *
from .logging_utils import *
from .sys_utils import *
from .snippet_db import SnippetDB

import sys
if sys.platform == "win32":
    from .reg_utils import *