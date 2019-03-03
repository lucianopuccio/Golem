import os
import json
import time
from types import SimpleNamespace

import pytest

from golem.core import tags_manager


class TestFilterTestsByTags:

    @pytest.fixture(scope="class")
    def _project_with_tags(self, project_class, test_utils):
        """A fixture of a project with tests that contain tags"""
        testdir = project_class.testdir
        project = project_class.name
        tests = SimpleNamespace()
        tests.test_alfa_bravo = 'test_alfa_bravo'
        content = 'tags = ["alfa", "bravo"]'
        test_utils.create_test(testdir, project, [], tests.test_alfa_bravo, content=content)
        tests.test_bravo_charlie = 'test_bravo_charlie'
        content = 'tags = ["bravo", "charlie"]'
        test_utils.create_test(testdir, project, [], tests.test_bravo_charlie, content=content)
        tests.test_delta_echo_foxtrot = 'test_delta_echo_foxtrot'
        content = 'tags = ["delta", "echo", "fox trot"]'
        test_utils.create_test(testdir, project, [], tests.test_delta_echo_foxtrot, content=content)
        tests.test_empty_tags = 'test_empty_tags'
        content = 'tags = []'
        test_utils.create_test(testdir, project, [], tests.test_empty_tags, content=content)
        tests.test_no_tags = 'test_no_tags'
        content = 'def test(data):\n     pass'
        test_utils.create_test(testdir, project, [], tests.test_no_tags, content=content)
        project_class.tests = list(tests.__dict__)
        project_class.t = tests
        return project_class

    def test_filter_tests_by_tags(self, _project_with_tags):
        testdir = _project_with_tags.testdir
        project = _project_with_tags.name
        tests = _project_with_tags.tests
        t = _project_with_tags.t
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['alfa', 'bravo'])
        assert filtered == [t.test_alfa_bravo]
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['bravo'])
        assert sorted(filtered) == sorted([t.test_alfa_bravo, t.test_bravo_charlie])
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['alfa and bravo'])
        assert filtered == [t.test_alfa_bravo]
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['"alfa" and "bravo"'])
        assert filtered == [t.test_alfa_bravo]
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['alfa or bravo'])
        assert sorted(filtered) == sorted([t.test_alfa_bravo, t.test_bravo_charlie])
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['bravo and not alfa'])
        assert filtered == [t.test_bravo_charlie]
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['(alfa or bravo) and charlie'])
        assert filtered == [t.test_bravo_charlie]
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['bravo or delta and not charlie'])
        assert sorted(filtered) == sorted([t.test_alfa_bravo, t.test_bravo_charlie, t.test_delta_echo_foxtrot])
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['(bravo or delta) and not charlie'])
        assert sorted(filtered) == sorted([t.test_alfa_bravo, t.test_delta_echo_foxtrot])

        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ["fox trot"])
        assert sorted(filtered) == sorted([t.test_delta_echo_foxtrot])

        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ["delta", "fox trot"])
        assert sorted(filtered) == sorted([t.test_delta_echo_foxtrot])

        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['"delta" or "fox trot"'])
        assert sorted(filtered) == sorted([t.test_delta_echo_foxtrot])
        filtered = tags_manager.filter_tests_by_tags(testdir, project, tests, ['bravo and echo'])
        assert filtered == []

    def test_filter_tests_by_tags_empty_list(self, _project_with_tags):
        filtered = tags_manager.filter_tests_by_tags(_project_with_tags.testdir,
                                                     _project_with_tags.name,
                                                     _project_with_tags.tests,
                                                     tags=[])
        assert filtered == []

    def test_filter_tests_by_tags_invalid_query(self, _project_with_tags):
        with pytest.raises(tags_manager.InvalidTagExpression) as excinfo:
            tags_manager.filter_tests_by_tags(_project_with_tags.testdir,
                                              _project_with_tags.name,
                                              _project_with_tags.tests,
                                              tags=['foo = 2'])
        expected = ("unknown expression <class '_ast.Assign'>, the only valid "
                    "operators for tag expressions are: 'and', 'or' & 'not'")
        assert expected in str(excinfo.value)


class TestGetTestsTags:

    def test_get_tests_tags(self, project_function, test_utils):
        testdir = project_function.testdir
        project = project_function.name
        # empty test list
        tags = tags_manager.get_tests_tags(testdir, project, [])
        assert tags == {}
        content = 'tags = ["foo", "bar"]'
        test_utils.create_test(testdir, project, parents=[], name='test_tags_001', content=content)
        # test tags for one test
        tags = tags_manager.get_tests_tags(testdir, project, ['test_tags_001'])
        assert tags == {'test_tags_001': ["foo", "bar"]}
        # test without tags returns empty list
        test_utils.create_test(testdir, project, parents=[], name='test_tags_002')
        tags = tags_manager.get_tests_tags(testdir, project, ['test_tags_001', 'test_tags_002'])
        assert tags['test_tags_002'] == []

    def test_get_tests_tags_verify_cache(self, project_function, test_utils):
        testdir = project_function.testdir
        project = project_function.name
        test_name = 'test_tags_003'
        content = 'tags = ["foo", "bar"]'
        test_path = test_utils.create_test(testdir, project, parents=[], name=test_name,
                                           content=content)
        # verify cache file does not exist and is created afterwards
        cache_path = os.path.join(testdir, 'projects', project, '.tags')
        assert not os.path.isfile(cache_path)
        tags = tags_manager.get_tests_tags(testdir, project, [test_name])
        assert os.path.isfile(cache_path)
        assert tags[test_name] == ["foo", "bar"]
        # verify that when a test is updated, the cache is updated as well
        time.sleep(0.3)  # give it some time!
        content = 'tags = ["baz"]'
        with open(test_path, 'w') as f:
            f.write(content)
        tags = tags_manager.get_tests_tags(testdir, project, [test_name])
        with open(cache_path) as f:
            cache = json.load(f)
            assert cache[test_name]['tags'] == ['baz']
        assert tags[test_name] == ['baz']


class TestGetAllProjectTestsTags:

    def test_get_all_project_tests_tags(self, project_function, test_utils):
        testdir = project_function.testdir
        project = project_function.name
        # no tests
        tags = tags_manager.get_all_project_tests_tags(testdir, project)
        assert tags == {}
        # with tests
        content = 'tags = ["foo", "bar"]'
        test_utils.create_test(testdir, project, parents=[], name='test001', content=content)
        content = 'tags = ["001", "002"]'
        test_utils.create_test(testdir, project, parents=[], name='test002', content=content)
        tags = tags_manager.get_all_project_tests_tags(testdir, project)
        assert tags == {'test001': ['foo', 'bar'], 'test002': ['001', '002']}


class TestGetProjectUniqueTags:

    def test_get_project_unique_tags(self, project_function, test_utils):
        testdir = project_function.testdir
        project = project_function.name
        content = 'tags = ["foo", "bar"]'
        test_utils.create_test(testdir, project, parents=[], name='test001', content=content)
        content = 'tags = ["bar", "baz"]'
        test_utils.create_test(testdir, project, parents=[], name='test002', content=content)
        tags = tags_manager.get_project_unique_tags(testdir, project)
        assert sorted(tags) == sorted(['foo', 'bar', 'baz'])
