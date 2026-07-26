import sys
from pathlib import Path

# Add parent directory to Python path so 'src' becomes importable
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))