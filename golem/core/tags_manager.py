import ast
import json
import os
import time

from golem.core import utils, file_manager


class InvalidTagExpression(Exception):
    pass


class TagExpressionConstructor:
    """Construct a boolean expression string for querying tags.
    The expression string can only contain:
      - and       (ast.BoolOp, ast.And)
      - or        (ast.BoolOp, ast.Or)
      - not       (ast.UnaryOp, ast.Not)
      - strings   (ast.Str)
      - names     (ast.Name)
      - numbers   (ast.Num)
    Any other ast node type will throw InvalidTagExpression

    Example:
      >> expression = "'foo' and (bar or not 'b a z')"
      >> tags = []
      >> TagExpressionConstructor(expression, tags).run()
      "('foo' in []) and (('bar' in []) or (not 'b a z' in []))"
    """
    def __init__(self, expression, tags):
        self.parsed = ast.parse(expression)
        self.tags = tags

    def run(self):
        return self._evaluate(self.parsed.body[0])

    def _evaluate(self, expr):
        if isinstance(expr, ast.Expr):
            return self._evaluate(expr.value)
        elif isinstance(expr, ast.BoolOp):
            if isinstance(expr.op, ast.Or):
                evaluated = ['({})'.format(self._evaluate(v)) for v in expr.values]
                return ' or '.join(evaluated)
            elif isinstance(expr.op, ast.And):
                evaluated = ['({})'.format(self._evaluate(v)) for v in expr.values]
                return ' and '.join(evaluated)
        elif isinstance(expr, ast.UnaryOp):
            if isinstance(expr.op, ast.Not):
                return 'not {}'.format(self._evaluate(expr.operand))
        elif isinstance(expr, ast.Num):
            return '"{}" in {}'.format(str(expr.n), self.tags)
        elif isinstance(expr, ast.Str):
            return '"{}" in {}'.format(expr.s, self.tags)
        elif isinstance(expr, ast.Name):
            return '"{}" in {}'.format(expr.id, self.tags)
        else:
            msg = ('unknown expression {}, the only valid operators for tag expressions '
                   'are: \'and\', \'or\' & \'not\''.format(type(expr)))
            raise InvalidTagExpression(msg)


def filter_tests_by_tags(workspace, project, tests, tags):
    """Filter a list of tests by a list of tags.

    Tags are concatenated with `and` operator.

    A tag can be a string that evals to a boolean expression.
    Only `and`, `or`, and `not` operators are allowed.
    Example:
      tags=["'foo' and ('bar' or not 'baz')"]

    Using an invalid tag expression will cause InvalidTagExpression
    """

    def _construct_tag_expr(tags):
        cleaned = []
        for tag in tags:
            try:
                ast.parse(tag)
                cleaned.append(tag)
            except SyntaxError:
                cleaned.append('"{}"'.format(tag))
        return ' and '.join(cleaned)

    def _test_matches_tag_query(query, tags):
        result = TagExpressionConstructor(query, tags).run()
        return eval(result)

    result = []
    tag_expr = _construct_tag_expr(tags)
    tests_tags = get_tests_tags(workspace, project, tests)
    if tag_expr:
        for test in tests:
            # tags_in_test = get_tests_tags(workspace, project, [test])
            if _test_matches_tag_query(tag_expr, tests_tags[test]):
                result.append(test)
    return result


def get_test_tags(workspace, project, full_test_case_name):
    result = []
    tc_name, parents = utils.separate_file_from_parents(full_test_case_name)
    path = os.path.join(workspace, 'projects', project, 'tests',
                        os.sep.join(parents), '{}.py'.format(tc_name))
    test_module, _ = utils.import_module(path)

    if hasattr(test_module, 'tags'):
        result = getattr(test_module, 'tags')

    return result


def get_tests_tags(workspace, project, tests):
    """Get the tags of a list of tests

    Caches the results.
    Updates the cache when last modification time of file differs
    from cache timestamp.
    """
    cache_file_path = os.path.join(workspace, 'projects', project, '.tags')
    cache_tags = {}
    if os.path.isfile(cache_file_path):
        with open(cache_file_path) as f:
            cache_tags = json.load(f)
    for test in tests:
        if test in cache_tags:
            # check if test file modification date > cache file timestamp:
            cache_timestamp = cache_tags[test]['timestamp']
            tc_name, parents = utils.separate_file_from_parents(test)
            path = os.path.join(workspace, 'projects', project, 'tests',
                                os.sep.join(parents), '{}.py'.format(tc_name))
            last_modified_time = os.path.getmtime(path)
            if last_modified_time != cache_timestamp:
                # re-read tags
                timestamp = time.time()
                cache_tags[test] = {
                    'tags': get_test_tags(workspace, project, test),
                    'timestamp': timestamp
                }
        else:
            timestamp = time.time()
            cache_tags[test] = {
                'tags': get_test_tags(workspace, project, test),
                'timestamp': timestamp
            }
    with open(cache_file_path, 'w') as f:
        json.dump(cache_tags, f, indent=4)
    tags = {test: cache_tags[test]['tags'] for test in cache_tags}
    return tags


def get_all_project_tests_tags(workspace, project):
    """Get all the tags of each test in a project"""
    tests_folder_path = os.path.join(workspace, 'projects', project, 'tests')
    tests = file_manager.get_files_dot_path(tests_folder_path, extension='.py')
    return get_tests_tags(workspace, project, tests)


def get_project_unique_tags(workspace, project):
    """Get a list of the unique tags used by all the tests of a project"""
    tests_tags = get_all_project_tests_tags(workspace, project)
    unique_tags = []
    for test, tags in tests_tags.items():
        for tag in tags:
            if tag not in unique_tags:
                unique_tags.append(tag)
    return unique_tags
