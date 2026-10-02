
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def mock_llm_nodes():
    from app.nodes import Intent, CandidateList
    with patch('app.nodes.get_llm') as mock_get_llm:
        mock_model = MagicMock()
        mock_get_llm.return_value = mock_model
        
        # We need structured output mocks for different nodes

        def with_structured_output(schema):
            mock_structured = MagicMock()
            def mock_invoke(prompt, *args, **kwargs):
                if schema.__name__ == 'Intent':
                    loc = 'fakemakecity' if 'fakemakecity' in str(prompt) else 'Bhopal'
                    return Intent(location=loc, activity='cycling', target_day=0, in_scope=True)
                elif schema.__name__ == 'CandidateList':
                    return CandidateList(sop_ids=['WIND-CYCLE-01', 'FUZZY-PICNIC-01'])
            mock_structured.invoke = mock_invoke
            return mock_structured

            
        mock_model.with_structured_output = with_structured_output
        
        # Regular invoke for compose_reply
        mock_result = MagicMock()
        mock_result.content = 'Matched WIND-CYCLE-01.'
        mock_model.invoke.return_value = mock_result
        
        yield
