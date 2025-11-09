"""
Shared XML generation logic for the Flatten tool.
Provides common functionality for creating structured XML output
from both local directories and GitHub repositories.
"""

import xml.dom.minidom as md
import xml.etree.ElementTree as ET
from typing import TypeAlias, Callable
from collections.abc import Iterable

XMLString: TypeAlias = str

# Common exclude patterns (gitignore-style)
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "*.egg-info",
    ".DS_Store",
    ".venv",
    "venv",
    ".env",
    "cache",
    "*.pyc",
]

# File extensions to include
INCLUDE_EXTENSIONS = (".py", ".lua", ".jinja2")  # ".md"


def should_exclude_path(path: str) -> bool:
    """Check if a path should be excluded based on EXCLUDE_PATTERNS."""
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*."):
            if path.endswith(pattern[1:]):
                return True
        elif pattern in path:
            return True
    return False


def should_include_file(filename: str) -> bool:
    """Check if a file should be included based on extension."""
    return filename.endswith(INCLUDE_EXTENSIONS)


def create_directory_tree_xml(
    project_name: str,
    path_iterator: Callable[
        [], Iterable[tuple[str, str]]
    ],  # Returns (file_path, filename) tuples
) -> ET.Element:
    """
    Create an XML directory tree from a path iterator.

    Args:
        project_name: Name of the root project
        path_iterator: Function that yields (file_path, filename) tuples

    Returns:
        XML Element representing the directory tree
    """
    directory_tree = ET.Element("directory_tree")
    root_directory = ET.SubElement(directory_tree, "directory", name=project_name)

    # Track created directories: path -> element mapping
    dirs_created = {project_name: root_directory}

    for file_path, filename in path_iterator():
        # Skip if file should be excluded
        if should_exclude_path(file_path) or not should_include_file(filename):
            continue

        # Parse directory structure from file path
        path_parts = file_path.split("/")
        if len(path_parts) <= 1:
            # File in root directory
            current_dir = root_directory
            clean_path = filename
        else:
            # File in subdirectory - create nested structure
            current_dir = root_directory
            current_path = project_name

            # Create nested directories as needed
            for dir_name in path_parts[:-1]:
                dir_path = current_path + "/" + dir_name
                if dir_path not in dirs_created:
                    new_dir = ET.SubElement(current_dir, "directory", name=dir_name)
                    dirs_created[dir_path] = new_dir
                    current_dir = new_dir
                else:
                    current_dir = dirs_created[dir_path]
                current_path = dir_path

            clean_path = "/".join(path_parts)

        # Add file to the XML structure
        ET.SubElement(current_dir, "file", name=filename, path=clean_path)

    return directory_tree


def create_file_contents_xml(
    file_reader: Callable[[str], str],  # Function that reads file content by path
    path_iterator: Callable[
        [], Iterable[tuple[str, str]]
    ],  # Returns (file_path, filename) tuples
) -> ET.Element:
    """
    Create an XML file contents section with CDATA.

    Args:
        file_reader: Function that takes a file path and returns content string
        path_iterator: Function that yields (file_path, filename) tuples

    Returns:
        XML Element with file contents in CDATA sections
    """
    root = ET.Element("file_contents")

    # Collect relevant files
    relevant_files = []
    for file_path, filename in path_iterator():
        if should_exclude_path(file_path) or not should_include_file(filename):
            continue
        relevant_files.append(file_path)

    # Create basic XML structure first
    file_elements = []
    for file_path in relevant_files:
        file_elem = ET.SubElement(root, "file", path=file_path)
        file_elements.append((file_path, file_elem))

    # Convert to string and parse with minidom to add CDATA
    xml_str = ET.tostring(root, encoding="unicode")
    dom = md.parseString(xml_str)

    # Add CDATA sections to each file element
    for i, (file_path, _) in enumerate(file_elements):
        try:
            content = file_reader(file_path)
            file_element = dom.getElementsByTagName("file")[i]
            cdata = dom.createCDATASection(content)
            file_element.appendChild(cdata)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")

    # Convert back to ElementTree
    new_root = ET.fromstring(dom.toxml())
    return new_root


def package_to_xml(
    project_name: str,
    file_reader: Callable[[str], str],
    path_iterator: Callable[[], Iterable[tuple[str, str]]],
) -> XMLString:
    """
    Create a complete XML package with directory tree and file contents.

    Args:
        project_name: Name of the project
        file_reader: Function that reads file content by path
        path_iterator: Function that yields (file_path, filename) tuples

    Returns:
        Formatted XML string
    """
    # Create the root project element
    root = ET.Element("project", name=project_name)

    # Get directory structure
    dir_tree = create_directory_tree_xml(project_name, path_iterator)
    root.append(dir_tree)

    # Get file contents
    file_contents = create_file_contents_xml(file_reader, path_iterator)
    root.append(file_contents)

    # Format and return
    return format_xml(root)


def format_xml(root_element: ET.Element) -> XMLString:
    """
    Format an XML element as a pretty-printed string.

    Args:
        root_element: The root XML element to format

    Returns:
        Pretty-printed XML string
    """
    # Convert to string with proper formatting
    rough_string = ET.tostring(root_element, encoding="unicode")

    # Use minidom to prettify
    dom = md.parseString(rough_string)
    pretty_xml = dom.toprettyxml(indent="  ")

    return pretty_xml
