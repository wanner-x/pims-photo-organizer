import inspect

import pims_v1.api.operations as operations_api
import pims_v1.api.progress as progress_api
import pims_v1.api.review as review_api
import pims_v1.api.tasks as tasks_api
import pims_v1.main as main_api


def test_api_request_sessions_do_not_run_schema_checks():
    for module in (main_api, operations_api, progress_api, review_api, tasks_api):
        source = inspect.getsource(module.get_session)

        assert "ensure_database_schema" not in source
