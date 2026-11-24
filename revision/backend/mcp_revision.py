"""Lance le serveur MCP « Révision » (utilisé par l'application Claude, voir connecter_claude.bat)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.mcp_server import main  # noqa: E402

main()
