"""Test the jobs embedded in the documentation's filters.rst file by running them against the data in the
data/doc_filer_testadata.yaml file."""
import importlib.util
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.utils

import pytest

import yaml

from webchanges.filters import FilterBase
from webchanges.handler import JobState
from webchanges.jobs import JobBase
from webchanges.storage import YamlJobsStorage

logger = logging.getLogger(__name__)

here = Path(__file__).parent
data_dir = here.joinpath('data')
docs_dir = here.joinpath('..').resolve().joinpath('docs')

latest_py_only = pytest.mark.skipif(sys.version_info < (3, 9), reason='Only needs to run once')


# https://stackoverflow.com/a/48719723/1047040
def parse_rst(text: str) -> docutils.nodes.document:
    """Parse the rst document."""
    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(components=components).get_default_values()
    document = docutils.utils.new_document('<rst-doc>', settings=settings)
    parser.parse(text, document)
    return document


# https://stackoverflow.com/a/48719723/1047040
class YAMLCodeBlockVisitor(docutils.nodes.NodeVisitor):
    """Used in loading yaml code block from rst file."""

    def __init__(self, doc):
        super().__init__(doc)
        self.code = []

    def visit_literal_block(self, node: docutils.nodes.reference) -> None:
        if 'python' in node.attributes['classes']:
            self.code.append(node.astext())

    def unknown_visit(self, node: docutils.nodes.Node) -> None:
        ...


def load_hooks_from_doc() -> str:
    """Load YAML code blocks from rst file."""
    doc = parse_rst(open(docs_dir.joinpath('hooks.rst')).read())
    visitor = YAMLCodeBlockVisitor(doc)
    doc.walk(visitor)
    return visitor.code[0]


def load_hooks_testdata() -> Dict[str, Any]:
    yaml_data = Path(data_dir.joinpath('doc_hooks_testdata.yaml')).read_text()
    return yaml.safe_load(yaml_data)


def load_hooks_jobs() -> List[JobBase]:
    jobs_file = data_dir.joinpath('doc_hooks_jobs.yaml')
    jobs_storage = YamlJobsStorage(jobs_file)
    return jobs_storage.load()


HOOKS_DOC_JOBS = load_hooks_jobs()
testdata = load_hooks_testdata()

HOOKS = load_hooks_from_doc()
spec = importlib.util.spec_from_loader('hooks', loader=None)
hooks = importlib.util.module_from_spec(spec)
sys.modules['hooks'] = hooks
exec(HOOKS, hooks.__dict__)  # nosec: B102 Use of exec detected.
# TODO: ensure that this is the version loaded during testing.


@latest_py_only
def test_flake8(tmp_path):
    """Check that the hooks.py example code in hooks.rst passes flake8."""
    hooks_path = tmp_path.joinpath('hooks.py')
    hooks_path.write_text(HOOKS)
    r = subprocess.run(['flake8', '--extend-ignore', 'W292', hooks_path], capture_output=True, text=True)  # nosec: B607
    assert r.stdout == ''
    assert not r.returncode


@pytest.mark.parametrize('job', HOOKS_DOC_JOBS)
def test_url(job: JobBase):
    d = testdata[job.url]
    data = d['input']
    job_state = JobState(None, job)
    data = FilterBase.auto_process(job_state, data)
    for filter_kind, subfilter in FilterBase.normalize_filter_list(job_state.job.filter):
        data = FilterBase.process(filter_kind, subfilter, job_state, data)

    expected_output_data = d['output']
    assert data == expected_output_data
