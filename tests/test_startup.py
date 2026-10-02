import os
import sys
import pytest
from unittest.mock import patch

def test_startup_key_check_reads_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=dummy_key_from_dotenv\nLLM_MODEL=gemini-3.5-flash\nLLM_PROVIDER=google_genai\nSOP_DIR=sops")
    
    # We create a dummy sops dir so load_sops doesn't crash during app import
    sops_dir = tmp_path / "sops"
    sops_dir.mkdir(exist_ok=True)
    (sops_dir / "dummy.yaml").write_text("id: DUMMY-01\ntitle: a\ncategory: general\nseverity: info\ndescription: a\napplies_to: ['*']\nconditions: {all: [{field: wind_gusts_10m, agg: max, scope: window, op: '>=', value: 40}]}\nadvice: a\nfacts_used: [wind_gusts_10m]")
    
    with patch.dict(os.environ, clear=True):
        # We need to make sure the app sees our dummy sops dir
        os.environ["SOP_DIR"] = str(sops_dir)
        
        # Patch find_dotenv so load_dotenv() uses our temp .env file
        with patch('dotenv.main.find_dotenv', return_value=str(env_file)):
            
            # Force re-import of app.main and app.config to trigger load_dotenv() and startup checks
            to_remove = [mod for mod in sys.modules if mod.startswith('app.') or mod.startswith('scripts.')]
            for mod in to_remove:
                del sys.modules[mod]
                
            # If the check fails, this import will raise RuntimeError.
            # If it passes, it proves the key was read from the temp .env.
            import app.main
            import scripts.try_chat
            
            assert os.getenv("GOOGLE_API_KEY") == "dummy_key_from_dotenv"
