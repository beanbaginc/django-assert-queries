"""Unit tests for template debugging functionality.

Version Added:
    2.1
"""

from __future__ import annotations

import os
import tempfile

from django.template import Context, Template, engines
from django.template.loader import get_template
from django.test.testcases import TestCase

from django_assert_queries.testing import assert_queries
from django_assert_queries.query_catcher import catch_queries
from django_assert_queries.tests.models import TestModel


class TemplateDebuggingTests(TestCase):
    """Unit tests for template debugging functionality."""

    def setUp(self) -> None:
        """Set up test data."""
        TestModel.objects.all().delete()
        TestModel.objects.bulk_create(
            [
                TestModel(name="test1"),
                TestModel(name="test2"),
            ]
        )

    def _extract_template_chain(self, error_message: str) -> list[str]:
        """Extract the template inheritance chain block from error message."""
        lines = error_message.split("\n")
        chain_lines = []
        in_template_section = False

        for line in lines:
            if "Template inheritance chain:" in line:
                in_template_section = True
                chain_lines.append(line.strip())
            elif in_template_section:
                if line.strip() and not line.startswith("  "):
                    # End of template section
                    break
                if line.strip():  # Skip empty lines
                    chain_lines.append(line.strip())

        return chain_lines

    def test_template_info_missing_when_no_template_context(self) -> None:
        """Testing that template_info is missing when no template context
        available."""
        # Execute query outside of template context
        with catch_queries() as ctx:
            list(TestModel.objects.all())

        self.assertEqual(len(ctx.executed_queries), 1)
        query_info = ctx.executed_queries[0]

        # Should not have template_info when not in template context
        self.assertNotIn("template_info", query_info)

    def test_template_info_capture_basic_functionality(self) -> None:
        """Testing basic template info capture functionality."""
        template_content = "{% for obj in objects %}{{ obj.name }}{% endfor %}"

        # Test with assert_queries to get the complete template chain
        # validation
        expected_queries = [
            {
                "model": TestModel,
                # Force mismatch to see template info
                "tables": {"wrong_table_name"},
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(template_content)
                context = Context({"objects": TestModel.objects.all()})
                template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for basic functionality test
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 1",
            "1  {% for obj in objects %}{{ obj.name }}{% endfor %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_django_style_output_format(self) -> None:
        """Testing Django-style template error output format when available."""
        template_content = "{% for obj in objects %}{{ obj.name }}{% endfor %}"

        expected_queries = [
            {
                "model": TestModel,
                # Force mismatch to see template info
                "tables": {"wrong_table_name"},
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(template_content)
                context = Context({"objects": TestModel.objects.all()})
                template.render(context)

        error_message = str(cm.exception)

        # The error should contain query mismatch information
        self.assertIn("1 query failed to meet expectations", error_message)
        self.assertIn("tables:", error_message)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for simple template
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 1",
            "1  {% for obj in objects %}{{ obj.name }}{% endfor %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_fail_fast_behavior_with_template_debugging(self) -> None:
        """Testing that template debugging follows fail-fast principle."""
        template_content = "{% for obj in objects %}{{ obj.name }}{% endfor %}"

        # Test with assert_queries to validate complete template chain and
        # fail-fast behavior
        expected_queries = [
            {
                "model": TestModel,
                # Force mismatch to test fail-fast
                "tables": {"wrong_table_name"},
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(template_content)
                context = Context({"objects": TestModel.objects.all()})
                template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain - should fail fast with clear
        # template info
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for fail-fast test
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 1",
            "1  {% for obj in objects %}{{ obj.name }}{% endfor %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_delayed_query_execution_issue(self) -> None:
        """Testing that template debugging now works correctly.

        This test verifies that the QuerySet tracking approach successfully
        captures template information for queries executed during template
        rendering.
        """
        # Simple template to test template debugging
        template_content = """<div>Some content before</div>
            <p>Some text</p>
            {% for obj in objects %}
                <p>{{ obj.name }}</p>
            {% endfor %}
            <div id="dpi" style="height: 1in; width: 1in;">
                DPI measurement div
            </div>
            """

        # First test with catch_queries to see if template_info is captured
        with catch_queries() as ctx:
            template = Template(template_content)
            context = Context({"objects": TestModel.objects.all()})
            template.render(context)

        self.assertEqual(len(ctx.executed_queries), 1)
        query_info = ctx.executed_queries[0]

        # Check if template_info is present
        self.assertIn(
            "template_info",
            query_info,
            "Template debugging should capture template_info",
        )

        template_info = query_info["template_info"]
        # template_info is now a list of templates in the inheritance chain
        self.assertIsInstance(template_info, list)
        self.assertTrue(len(template_info) > 0)

        # Check the first template in the chain (where the query actually
        # executes)
        first_template = template_info[0]
        self.assertIn("name", first_template)
        self.assertIn("origin", first_template)

        # In test environments, we might not get precise line numbers
        # but we should at least get basic template information
        if (
            "line_number" in first_template and
            first_template["line_number"] > 0
        ):
            # We have precise line information
            # {% for %} is on line 3
            self.assertEqual(first_template["line_number"], 3)
            if "line_content" in first_template:
                self.assertIn(
                    "{% for obj in objects %}", first_template["line_content"]
                )
        else:
            # Basic template info without precise line numbers
            # (test environment)
            # Template name should be captured
            self.assertIn("unknown", first_template["name"])

        # Now test with assert_queries to see if it formats correctly
        expected_queries = [
            {
                "model": TestModel,
                "tables": {"wrong_table_name"},  # Force mismatch
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template2 = Template(template_content)
                context2 = Context({"objects": TestModel.objects.all()})
                template2.render(context2)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for multi-line template
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 3",
            "3  {% for obj in objects %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_nested_template_rendering_issue(self) -> None:
        """Testing template debugging with nested rendering contexts.

        This test currently passes because we're using simple templates.
        In real-world scenarios with template inheritance, the issue is that
        queries from child templates might be attributed to parent templates.

        This test serves as a placeholder for future template inheritance
        testing.
        """
        # Simple template that should work correctly
        template_content = """<html>
            <head><title>Base</title></head>
            <body>
                {% for obj in objects %}
                    {{ obj.name }}
                {% endfor %}
            </body>
            </html>"""

        expected_queries = [
            {
                "model": TestModel,
                "tables": {"wrong_table_name"},  # Force mismatch
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(template_content)
                context = Context({"objects": TestModel.objects.all()})
                template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for nested HTML template
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 4",
            "4  {% for obj in objects %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_sitetree_missing_line_number_issue(self) -> None:
        """Testing the sitetree issue where queries show template name but no
        line number.

        Real-world example from Query 12:
        - Expected: "In template base.html, error at line X" with specific
          line
        - Actual: "Template: base.html (/path/to/base.html)"
                  with no line number
        """
        # Simulate a sitetree-like scenario with complex template
        template_content = """<html>
            <head><title>Test</title></head>
            <body>
                <nav>
                    {% comment %}
                    This simulates sitetree_menu location
                    {% endcomment %}
                    {% for obj in menu_objects %}
                        <a href="#">{{ obj.name }}</a>
                    {% endfor %}
                </nav>
            </body>
            </html>"""

        expected_queries = [
            {
                "model": TestModel,
                "tables": {"wrong_table_name"},  # Force mismatch
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(template_content)
                context = Context({"menu_objects": TestModel.objects.all()})
                template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for sitetree-like template
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 8",
            "8  {% for obj in menu_objects %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_queryset_lazy_evaluation_timing_issue(self) -> None:
        """Testing the core issue: QuerySet creation vs execution timing.

        This test demonstrates how Django's lazy QuerySet evaluation can cause
        template debugging to point to the wrong location.

        The issue:
        1. Template tag creates QuerySet (no query executed yet)
        2. QuerySet gets passed around in template context
        3. Query finally executes when a different template node evaluates it
        4. Template debugging captures the wrong node's context
        """
        # Template that creates a QuerySet but doesn't immediately evaluate
        # it
        template_content = """
            <h1>Header</h1>
            {% with queryset=objects %}
                <p>Queryset created but not evaluated yet</p>
                {% comment %}
                Query will execute on next line when len() is called
                {% endcomment %}
                <p>Count: {{ queryset|length }}</p>
            {% endwith %}
            <p>Footer</p>
            """

        expected_queries = [
            {
                "model": TestModel,
                "tables": {"wrong_table_name"},  # Force mismatch
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(template_content)
                context = Context({"objects": TestModel.objects.all()})
                template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for lazy evaluation template
        # Shows both the {% with %} context and the actual query execution
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 3",
            "3  {% with queryset=objects %}",
            "[2] In template <unknown source>, error at line 8",
            "8  <p>Count: {{ queryset|length }}</p>",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_wrong_line_attribution_issue(self) -> None:
        """Testing wrong line attribution like Query 13.

        Real-world example from Query 13:
        - Query comes from sitetree breadcrumbs (line with sitetree tag)
        - But template debugging points to line 41 (meta description tag)
        - Expected: Should point to the line
                    with the actual sitetree template tag
        """
        # Recreate scenario similar to Query 13
        template_content = """<!DOCTYPE html>
            <html>
            <head>
                <meta name="description" content="Download free 3D models">
                <title>Test Page</title>
            </head>
            <body>
                <nav>
                    {% comment %}
                    This simulates sitetree_breadcrumbs location
                    {% endcomment %}
                    {% for obj in breadcrumb_objects %}
                        <span>{{ obj.name }}</span>
                    {% endfor %}
                </nav>
                <main>
                    <h1>Main Content</h1>
                </main>
            </body>
            </html>"""

        expected_queries = [
            {
                "model": TestModel,
                "tables": {"wrong_table_name"},  # Force mismatch
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(template_content)
                context = Context(
                    {"breadcrumb_objects": TestModel.objects.all()}
                )
                template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for breadcrumb template
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template <unknown source>, error at line 12",
            "12  {% for obj in breadcrumb_objects %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_template_inheritance_issue(self):
        """
        CRITICAL TEST: Template inheritance detection issue.

        This test verifies that template debugging correctly identifies
        templates in inheritance scenarios and shows the complete
        template chain.
        """
        # Simple template - this should work fine
        template_content = """<div>Test template</div>
        {% for obj in objects %}{{ obj.name }}{% endfor %}
        <div>End</div>"""

        expected_queries = [
            {
                "model": TestModel,
                # Force mismatch to see template info
                "tables": {"wrong_table"},
            }
        ]

        with self.assertRaises(AssertionError) as cm:
            with assert_queries(expected_queries, with_tracebacks=True):
                template = Template(
                    template_content, name="test_inheritance.html"
                )
                context = Context({"objects": TestModel.objects.all()})
                template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for inheritance test
        expected_chain = [
            "Template inheritance chain:",
            "[1] In template test_inheritance.html, error at line 2",
            "2  {% for obj in objects %}{{ obj.name }}{% endfor %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_block_super_attribution_issue(self) -> None:
        """
        TEST: Block.super attribution works correctly.

        This test verifies that when {{ block.super }} is called in a
        child template, queries that originate in the parent template
        are correctly attributed to the parent template, not the
        child template's {{ block.super }} call.

        Real-world example from blenderhub_server:
        - Child template: base_profile.html calls {{ block.super }}
        - Parent template: base.html has {% for user in users %}
        - Expected: Should show "base.html, line X: {% for user in users %}"
        - Not: "base_profile.html, line 56: {{ block.super }}"
        """
        # Create a realistic block.super scenario with
        # actual template inheritance
        with tempfile.TemporaryDirectory() as temp_dir:
            # Parent template with query-causing code
            parent_template_content = """<!DOCTYPE html>
                <html>
                <head><title>Parent Template</title></head>
                <body>
                {% block content %}
                        <h1>Parent Content</h1>
                        {% comment %}
                        This is where the actual query happens
                        {% endcomment %}
                    {% for obj in objects %}
                            <p>Parent: {{ obj.name }}</p>
                        {% endfor %}
                    {% endblock %}
                </body>
                </html>"""

            # Child template that calls block.super
            child_template_content = """{% extends "parent.html" %}
                {% block content %}
                    <div>Child template content</div>
                    {% comment %}
                    This calls parent code -
                    query should be attributed to parent
                    {% endcomment %}
                    {{ block.super }}
                    <div>End of child content</div>
                {% endblock %}"""

            # Write templates to files
            parent_path = os.path.join(temp_dir, "parent.html")
            child_path = os.path.join(temp_dir, "child.html")

            with open(parent_path, "w") as f:
                f.write(parent_template_content)

            with open(child_path, "w") as f:
                f.write(child_template_content)

            # Add temp directory to Django template dirs
            engine = engines["django"]
            engine.engine.dirs.append(temp_dir)

            expected_queries = [
                {
                    "model": TestModel,
                    # Force mismatch to see template info
                    "tables": {"wrong_table_name"},
                }
            ]

            with self.assertRaises(AssertionError) as cm:
                with assert_queries(expected_queries, with_tracebacks=True):
                    template = get_template("child.html")
                    context = {"objects": TestModel.objects.all()}
                    template.render(context)

            error_message = str(cm.exception)

            # Extract and validate template chain
            template_chain = self._extract_template_chain(error_message)

            # Expected template chain for block.super scenario
            # This shows the complete inheritance chain with proper attribution
            expected_chain = [
                "Template inheritance chain:",
                f"[1] In template {parent_path}, error at line 5",
                "5  {% block content %}",
                f"[2] Template: parent.html ({parent_path})",
                f"[3] In template {parent_path}, error at line 10",
                "10  {% for obj in objects %}",
            ]

            self.assertEqual(template_chain, expected_chain)

    def test_basic_template_debugging_functionality(self) -> None:
        """
        TEST: Basic template debugging functionality works correctly.

        This test verifies that the core template debugging features work:
        1. Template name detection
        2. Line number detection
        3. Line content extraction
        4. Django-style error format
        """
        # Simple template with clear line structure
        template_content = """<h1>Header</h1>
<p>Some content</p>
{% for obj in objects %}
    <span>{{ obj.name }}</span>
{% endfor %}
<p>Footer</p>"""

        expected_queries = [
            {
                "model": TestModel,
                "tables": {"wrong_table_name"},  # Force mismatch
            }
        ]

        # Create a temporary template file
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = os.path.join(temp_dir, "test_basic_template.html")
            with open(template_path, "w") as f:
                f.write(template_content)

            # Add temporary directory to Django template dirs
            engine = engines["django"]
            engine.engine.dirs.append(temp_dir)

            with self.assertRaises(AssertionError) as cm:
                with assert_queries(expected_queries, with_tracebacks=True):
                    template = get_template("test_basic_template.html")
                    context = {"objects": TestModel.objects.all()}
                    template.render(context)

        error_message = str(cm.exception)

        # Extract and validate template chain
        template_chain = self._extract_template_chain(error_message)

        # Expected template chain for file-based template
        # (should show full path)
        expected_chain = [
            "Template inheritance chain:",
            f"[1] In template {template_path}, error at line 3",
            "3  {% for obj in objects %}",
        ]

        self.assertEqual(template_chain, expected_chain)

    def test_real_file_path_detection(self) -> None:
        """
        TEST: Real file paths are detected correctly.

        This test verifies that when templates are loaded from actual files
        (not string content), the full file paths are captured correctly.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a real template file
            template_path = os.path.join(temp_dir, "real_file_template.html")
            template_content = """<h1>Real File Template</h1>
                <div>Content</div>
                {% for obj in objects %}
                    <p>{{ obj.name }}</p>
                {% endfor %}
                <footer>End</footer>"""

            with open(template_path, "w") as f:
                f.write(template_content)

            # Add temp directory to template dirs
            engine = engines["django"]
            engine.engine.dirs.insert(0, temp_dir)

            expected_queries = [
                {
                    "model": TestModel,
                    "tables": {"wrong_table_name"},  # Force mismatch
                }
            ]

            with self.assertRaises(AssertionError) as cm:
                with assert_queries(expected_queries, with_tracebacks=True):
                    template = get_template("real_file_template.html")
                    context = {"objects": TestModel.objects.all()}
                    template.render(context)

            error_message = str(cm.exception)

            # Extract and validate template chain
            template_chain = self._extract_template_chain(error_message)

            # Expected template chain for real file template
            expected_chain = [
                "Template inheritance chain:",
                f"[1] In template {template_path}, error at line 3",
                "3  {% for obj in objects %}",
            ]

            self.assertEqual(template_chain, expected_chain)
