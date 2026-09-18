import os
import glob
import re

replacements = {
    # Tool names
    "read_log": "read_log",
    "search_doc": "search_doc",
    "restart_equipment": "restart_equipment",
    "send_email": "send_email",
    "write_file": "write_file",
    
    # Arguments
    "equipment": "equipment",
    "query": "query",
    "recipient": "recipient",
    "subject": "subject",
    "body": "body",
    "path": "path",
    "content": "content",
    
    # Equipment names
    "SENS-": "SENS-",
    "VALVE-": "VALVE-",
    "PUMP-": "PUMP-",
    "CTRL-": "CTRL-",
    
    # Some internal simulator messages
    "Email sent to": "Email sent to",
    "Email sent": "Email sent",
    "Written in": "Written in",
    "restarted": "restarted",
    "unknown tool": "unknown tool",
    "non-object response": "non-object response",
    "no usable JSON": "no usable JSON",
    "tool": "tool",
    "response": "response",
    "done": "done"
}

files_to_check = glob.glob("**/*.py", recursive=True) + glob.glob("**/*.md", recursive=True)
for file in files_to_check:
    if file.startswith("venv") or file.startswith(".venv") or file.startswith("logs"): continue
    
    with open(file, 'r') as f:
        content = f.read()
        
    new_content = content
    # Replace whole words for tool names and arguments
    for k, v in replacements.items():
        if '-' in k or ' ' in k:
            new_content = new_content.replace(k, v)
        else:
            # use regex for exact word boundary
            new_content = re.sub(r'\b' + k + r'\b', v, new_content)
            
    if content != new_content:
        with open(file, 'w') as f:
            f.write(new_content)
        print(f"Updated {file}")
