#!/usr/bin/env python3
"""
Test to ensure no emoji in Python files (Windows compatibility)

This test prevents regression - any new emoji added to the codebase
will cause this test to fail, reminding developers to use ASCII.
"""
import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from check_emoji import scan_project, is_emoji


class TestNoEmoji(unittest.TestCase):
    """Ensure no emoji in Python files for Windows compatibility"""
    
    def test_no_emoji_in_python_files(self):
        """All .py files should be free of emoji"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        results = scan_project(project_root)
        
        if results:
            msg_parts = ["Found emoji in Python files (Windows incompatible):"]
            for filepath, emoji_list in results.items():
                rel_path = os.path.relpath(filepath, project_root)
                for item in emoji_list:
                    msg_parts.append(f"  {rel_path}:{item['line']} - {repr(item['char'])}")
            
            self.fail("\n".join(msg_parts))
    
    def test_emoji_detection(self):
        """Test that emoji detection works correctly"""
        # Should detect these
        self.assertTrue(is_emoji('\U0001f4d0'))  # Triangular ruler
        self.assertTrue(is_emoji('\U0001f534'))  # Red circle
        self.assertTrue(is_emoji('\u2713'))      # Check mark
        
        # Should NOT detect these (Polish characters are OK in comments)
        self.assertFalse(is_emoji('a'))
        self.assertFalse(is_emoji('Z'))
        self.assertFalse(is_emoji('1'))


if __name__ == '__main__':
    unittest.main()
