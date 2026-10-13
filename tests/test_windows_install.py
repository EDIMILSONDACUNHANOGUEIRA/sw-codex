"""Instalação no Windows: dependências usadas pelo código e .bat que esperam o servidor."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WindowsInstall(unittest.TestCase):
    def test_requirements_cover_imports(self):
        names = {re.split(r"[<>=\[ ]", line.strip(), maxsplit=1)[0].lower()
                 for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")}
        for package in ("scipy", "httpx", "fastapi", "uvicorn", "python-multipart", "numpy", "pillow"):
            self.assertIn(package, names)

    def test_launchers_open_browser_only_after_server_answers(self):
        helper = ROOT / "scripts" / "esperar-e-abrir.ps1"
        self.assertIn("/api/status", helper.read_text(encoding="utf-8"))
        for name, port in (("abrir-noticias.bat", 8768), ("abrir-gameplay.bat", 8769), ("abrir-studio.bat", 8000)):
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn('esperar-e-abrir.ps1" -Url http://127.0.0.1:%d/' % port, text, name)
            self.assertNotRegex(text, r'(?m)^start "" http', name)
            # O servidor fica em primeiro plano, depois do script de espera.
            self.assertLess(text.index("esperar-e-abrir.ps1"), text.index("python -m"), name)


if __name__ == "__main__":
    unittest.main()
