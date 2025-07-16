#!/bin/python3
import os
import subprocess
import json
import requests
import sys
import datetime
import time
import shutil
import re
import platform
import tempfile
import signal
from threading import Thread, Event
from typing import List, Dict, Tuple, Optional
import readline
import atexit
import random

OPENROUTER_API_KEY = "your-api-key"
OPENROUTER_MODELS = [
    "mistralai/mistral-7b-instruct",
    "anthropic/claude-instant-1.2",
    "nousresearch/nous-hermes-2-mixtral-8x7b-sft",
    "openai/gpt-3.5-turbo",
    "google/gemini-pro"
]
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1/chat/completions"

class Colors:
    BLUE = "\033[1;34m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    CYAN = "\033[1;36m"
    PURPLE = "\033[1;35m"
    WHITE = "\033[1;37m"
    GRAY = "\033[1;90m"
    RESET = "\033[0m"

class Icons:
    PROMPT = f"{Colors.GREEN}⚡{Colors.RESET}"
    INFO = f"{Colors.BLUE}ℹ{Colors.RESET}"
    THINKING = f"{Colors.YELLOW}⌛{Colors.RESET}"
    ERROR = f"{Colors.RED}✖{Colors.RESET}"
    HELP = f"{Colors.CYAN}?{Colors.RESET}"
    COMMAND = f"{Colors.PURPLE}$>{Colors.RESET}"
    OUTPUT = f"{Colors.CYAN}↳{Colors.RESET}"
    ROOT = f"{Colors.RED}⚡{Colors.RESET}"
    SUCCESS = f"{Colors.GREEN}✓{Colors.RESET}"
    WARNING = f"{Colors.YELLOW}⚠{Colors.RESET}"

# --- Banner and UI Enhancements ---
BANNERS = [
    f"""{Colors.RED}
    ██████╗ ███████╗███╗  ██╗ █████╗ ██╗
  ██╔═══██╗██╔════╝████╗ ██║██╔══██╗██║
  ██║  ██║█████╗  ██╔██╗ ██║███████║██║
  ██║  ██║██╔══╝  ██║╚██╗██║██╔══██║██║
  ╚██████╔╝███████╗██║ ╚████║██║  ██║███████╗
    ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝
{Colors.RESET}""",

    f"""{Colors.CYAN}
  ██████╗ ███████╗███╗  ██╗ █████╗ ██╗
  ██╔═══██╗██╔════╝████╗ ██║██╔══██╗██║
  ██║  ██║█████╗  ██╔██╗ ██║███████║██║
  ██║  ██║██╔══╝  ██║╚██╗██║██╔══██║██║
  ╚██████╔╝███████╗██║ ╚████║██║  ██║███████╗
    ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝
{Colors.RESET}""",

    f"""{Colors.PURPLE}
  ╔═╗┬ ┬┌─┐┌─┐┬┌─  ╔═╗╔═╗╦═╗
  ╠═╝├─┤├─┤│  ├┴┐  ╠═╝║ ║╠╦╝
  ╩  ┴ ┴┴ ┴└─┘┴ ┴  ╩  ╚═╝╩╚═
{Colors.RESET}"""
]

def get_random_banner():
    """Return a random banner from the available options"""
    return random.choice(BANNERS)

MODEL_ROLE_TEMPLATE = """You are a highly efficient, concise, and direct terminal-based AI assistant for cybersecurity and ethical hacking, acting as a professional penetration tester.

Your operating environment: {os_info}

Your primary function is to:
1. Generate and provide executable shell commands (Bash) in Markdown code blocks (

bash\\ncommand here\\n

) ONLY WHEN THE USER EXPLICITLY ASKS YOU TO PERFORM AN ACTION.
2. Respond conversationally if the user is having a general conversation or asking a question not requiring immediate command execution.

IMPORTANT GUIDELINES:
* When a target is set, ALWAYS use the shell variable $TARGET in commands.
* If a command requires root privileges, clearly state "This command requires root privileges (sudo)."
* If no target is set, prompt the user to set one using 'set target <IP|URL>'.
* Guide through recon, enumeration, exploitation (if authorized), post-exploitation.
* For multi-step tasks, provide the first set of commands and wait for user feedback.
* If a command requires user interaction or long execution time, clearly state that.
* When providing commands for execution:
    * Frame your response conversationally, briefly stating what you will do.
    * The commands themselves should be enclosed in markdown blocks as usual.
    * If a new script or file is required (e.g., a Python script, a configuration file), **ensure to provide the commands to create that file first (e.g., using cat << 'EOF' > filename.py or echo '...' > filename.py) before attempting to execute or use the file.** This is critical: if the user asks you to "create a script" or "write a Python program", you MUST provide the file creation commands first, then indicate how to run it.
    * Your conversational response will be displayed only if no commands are generated. If commands ARE generated, the application will automatically extract and execute them without showing your full textual response to the user. Do NOT include phrases indicating you cannot execute commands, as the application handles execution directly.
* Do not propose or execute reconnaissance or scanning commands (e.g., nmap, masscan, dirb, gobuster, nikto, sqlmap in a scanning context, etc.) unless the user explicitly requests a scan, reconnaissance, or uses an affirmative phrase such as 'please scan', 'perform a scan', 'enumerate', 'find open ports', 'check for vulnerabilities', or similar. If the user asks for general advice on a target without such a specific request, provide information or ask clarifying questions instead of generating scan commands.
* Mention CVE references and exploitation techniques when applicable.
* Do not simulate terminal output.
* Explain commands briefly outside the code block if explanations are enabled.
"""
# --- Global Variables ---
conversation_history: List[Dict] = []
target_ip_url: str = ""
verbose_mode: bool = False
explanation_mode: bool = False
animation_stop_event = Event()
execution_interrupted_flag = Event()
current_model: str = OPENROUTER_MODELS[0]
output_dir: str = os.path.expanduser("~/.penai/output")

# --- Readline History Configuration ---
HISTORY_FILE = os.path.expanduser("~/.penai_history")
MAX_HISTORY_SIZE = 1000

def setup_readline():
    """Sets up command history using readline."""
    try:
        readline.read_history_file(HISTORY_FILE)
    except FileNotFoundError:
        pass
    
    readline.set_history_length(MAX_HISTORY_SIZE)
    atexit.register(readline.write_history_file, HISTORY_FILE)

# --- Helper Functions ---
def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_status():
    """Print current system status"""
    print(f"\n{Colors.CYAN}=== PenAI Status ==={Colors.RESET}")
    print(f"{Icons.INFO} Target: {Colors.YELLOW}{target_ip_url if target_ip_url else 'Not set'}{Colors.RESET}")
    print(f"{Icons.INFO} Model: {Colors.YELLOW}{current_model}{Colors.RESET}")
    print(f"{Icons.INFO} Verbose Command Output: {Colors.YELLOW}{verbose_mode}{Colors.RESET}")
    print(f"{Icons.INFO} AI Explanations: {Colors.YELLOW}{explanation_mode}{Colors.RESET}")
    print(f"{Icons.INFO} Output Directory: {Colors.YELLOW}{output_dir}{Colors.RESET}\n")

def animate_thinking(text: str = "Processing"):
    """Show a thinking animation"""
    chars = "⣾⣽⣻⢿⡿⣟⣯⣷"
    idx = 0
    while not animation_stop_event.is_set():
        print(f"\r{Icons.THINKING} {text} {chars[idx % len(chars)]}", end="", flush=True)
        idx += 1
        time.sleep(0.1)
    print("\r" + " " * (len(text) + 10) + "\r", end="", flush=True)

def log_message(message: str):
    """Log verbose messages"""
    if verbose_mode:
        print(f"{Icons.INFO} {Colors.GRAY}{message}{Colors.RESET}", file=sys.stderr)

def log_error(message: str):
    """Log error messages"""
    print(f"{Icons.ERROR} {Colors.RED}Error:{Colors.RESET} {message}", file=sys.stderr)

def log_warning(message: str):
    """Log warning messages"""
    print(f"{Icons.WARNING} {Colors.YELLOW}Warning:{Colors.RESET} {message}", file=sys.stderr)

def add_to_history(role: str, content: str):
    """Add message to conversation history"""
    conversation_history.append({"role": role, "content": content})

def check_root_privileges() -> bool:
    """Check if running with root privileges"""
    return os.geteuid() == 0

def remove_code_blocks(text: str) -> str:
    """Removes markdown code blocks (```...```) from a string."""
    cleaned_text = re.sub(r"```(bash|sh)?.*?```", "", text, flags=re.DOTALL)
    return cleaned_text.strip()

# --- Smart Execution Functions ---
def ai_executing(action: str, details: str = ""):
    """Display smart execution status with details"""
    if details:
        print(f"\n{Icons.THINKING} {action}... {Colors.GRAY}({details}){Colors.RESET}")
    else:
        print(f"\n{Icons.THINKING} {action}...{Colors.RESET}")

def ai_result(action: str, status: bool, details: str = "", summary: str = ""):
    """Display smart execution result with optional details and summary"""
    icon = Icons.SUCCESS if status else Icons.ERROR
    color = Colors.GREEN if status else Colors.RED
    
    print(f"\r{icon} {color}{action}: {'Success' if status else 'Failed'}{Colors.RESET}")
    
    if details:
        print(f"{Icons.INFO} {Colors.CYAN}Details:{Colors.RESET} {details}")
    
    if summary:
        print(f"{Icons.OUTPUT} {Colors.PURPLE}Summary:{Colors.RESET}\n{summary}")

# --- Installation Handling ---
def get_package_manager() -> Optional[str]:
    """Detect the system package manager"""
    system = platform.system()
    if system == "Linux":
        if shutil.which("apt-get"):
            return "apt-get"
        elif shutil.which("apt"):
            return "apt"
        elif shutil.which("dnf"):
            return "dnf"
        elif shutil.which("yum"):
            return "yum"
        elif shutil.which("pacman"):
            return "pacman"
        elif shutil.which("zypper"):
            return "zypper"
    elif system == "Darwin":
        if shutil.which("brew"):
            return "brew"
    return None

def check_tool_installed(tool_name: str) -> bool:
    """Check if a tool is installed and available in PATH"""
    # Special case for python which might be python3
    if tool_name == "python":
        return shutil.which("python") or shutil.which("python3")
    return bool(shutil.which(tool_name))

def install_tool_interactive(tool_name: str) -> bool:
    """Attempt to install a tool with user interaction"""
    pkg_manager = get_package_manager()
    if not pkg_manager:
        log_error("Could not determine package manager for this system")
        return False

    # Special case for python
    if tool_name == "python":
        tool_name = "python3"

    if pkg_manager in ["apt", "apt-get"]:
        cmd = f"sudo {pkg_manager} update && sudo {pkg_manager} install -y {tool_name}"
    elif pkg_manager in ["dnf", "yum"]:
        cmd = f"sudo {pkg_manager} install -y {tool_name}"
    elif pkg_manager == "pacman":
        cmd = f"sudo pacman -Sy --noconfirm {tool_name}"
    elif pkg_manager == "brew":
        cmd = f"brew install {tool_name}"
    else:
        log_error(f"Unsupported package manager: {pkg_manager}")
        return False

    print(f"{Icons.INFO} To install {tool_name}, run: {Colors.CYAN}{cmd}{Colors.RESET}")
    choice = input(f"{Icons.PROMPT} Run installation command? (Y/n): ").strip().lower()
    
    if choice not in ('', 'y', 'yes'):
        return False

    try:
        subprocess.run(cmd, shell=True, check=True)
        return check_tool_installed(tool_name)
    except subprocess.CalledProcessError as e:
        log_error(f"Installation failed: {e}")
        return False
    except Exception as e:
        log_error(f"Unexpected error during installation: {e}")
        return False

# --- Command Execution ---
def process_tool_output(tool_name: str, raw_output: str) -> str:
    """Process and filter tool output to keep it concise"""
    lines = raw_output.splitlines()
    filtered_output = []

    unwanted_patterns = [
        r"Starting Nmap \d+\.\d+",
        r"Nmap done: \d+ IP addresses",
        r"Warning: Hostname",
        r"For more information, see",
        r"Running: Nmap",
        r"Read data files from:",
        r"Service scan Timing:",
        r"PORTS:",
        r"HOST:",
        r"Latency:",
        r"Ignored",
        r"Not shown:",
        r"WARNING: No targets specified",
        r"QUITTING!",
        r"You are not required to provide consent",
        r"http-request-randomize",
        r"Connection reset by peer",
        r"seconds, finished",
        r"To use the Nmap Scripting Engine, specify",
        r"NOTE: the rDNS lookup will also resolve PTR records"
    ]

    for line in lines:
        if not any(re.search(pattern, line, re.IGNORECASE) for pattern in unwanted_patterns):
            if line.strip():
                filtered_output.append(line.strip())
    
    return "\n".join(filtered_output[:20])

def extract_commands(ai_response: str) -> List[str]:
    """Extract commands from AI response formatted in Markdown code blocks"""
    commands = []
    current_command = []
    in_code_block = False

    for line in ai_response.splitlines():
        if line.strip().startswith("```bash") or line.strip().startswith("```sh"):
            in_code_block = True
            continue
        elif line.strip() == "```" and in_code_block:
            in_code_block = False
            if current_command:
                commands.append("\n".join(current_command))
                current_command = []
            continue
        if in_code_block:
            current_command.append(line)

    return commands

def run_single_command(command_str: str, env_vars: Dict, output_buffer: Dict, tool_name: str):
    """
    Runs a single command in a subprocess and captures its output.
    Designed to be run in a separate thread.
    """
    process = None
    try:
        preexec_fn_arg = os.setsid if platform.system() != "Windows" else None

        process = subprocess.Popen(
            command_str,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env_vars,
            preexec_fn=preexec_fn_arg
        )

        stdout_lines = []
        stderr_lines = []

        while True:
            stdout_line = process.stdout.readline()
            stderr_line = process.stderr.readline()

            if stdout_line:
                stdout_lines.append(stdout_line)
            if stderr_line:
                stderr_lines.append(stderr_line)
            
            if not stdout_line and not stderr_line and process.poll() is not None:
                break

            if execution_interrupted_flag.is_set():
                log_message(f"Signaling process '{tool_name}' (PID {process.pid}) to terminate due to interruption.")
                try:
                    if platform.system() != "Windows" and process.pid:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    else:
                        process.terminate()
                except ProcessLookupError:
                    pass
                break
            
            time.sleep(0.05)

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log_error(f"Process '{tool_name}' did not terminate cleanly after signal.")
            try:
                if platform.system() != "Windows" and process and process.pid:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                elif process:
                    process.kill()
            except (ProcessLookupError, AttributeError):
                pass
            output_buffer["returncode"] = -2
        
        output_buffer["stdout"] = "".join(stdout_lines).strip()
        output_buffer["stderr"] = "".join(stderr_lines).strip()
        output_buffer["returncode"] = process.returncode if process.returncode is not None else -2

    except subprocess.TimeoutExpired:
        log_error(f"Command '{command_str}' timed out during setup or early execution.")
        output_buffer["returncode"] = -1
        output_buffer["stderr"] = "Command timed out during setup."
    except Exception as e:
        log_error(f"Error running command in thread '{command_str}': {e}")
        output_buffer["returncode"] = -1
        output_buffer["stderr"] = str(e)

def generate_and_save_report(command_results: List[Dict]):
    """Generates a summary report of executed commands and saves it."""
    if not command_results:
        print(f"{Icons.INFO} No commands were executed to generate a report.")
        return

    report_content = []
    report_content.append(f"--- PenAI Execution Report - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    report_content.append(f"Target: {target_ip_url if target_ip_url else 'N/A'}")
    report_content.append("-" * 60)

    for result in command_results:
        report_content.append(f"\nCommand: {result['command']}")
        report_content.append(f"Tool: {result['tool']}")
        report_content.append(f"Status: {result['status'].upper()}")
        report_content.append(f"Return Code: {result['returncode']}")
        if result['status'] == 'interrupted':
            report_content.append(f"Note: Command was interrupted by user.")
        report_content.append(f"Log File: {result['log_file']}")
        
        report_content.append("\n--- Summary/Error Output ---")
        filtered_summary = process_tool_output(result['tool'], result['stdout'])
        if filtered_summary:
            report_content.append(filtered_summary)
        if result['stderr']:
            report_content.append("\n--- STDERR ---")
            report_content.append(result['stderr'][:500] + ("..." if len(result['stderr']) > 500 else ""))
        if not filtered_summary and not result['stderr']:
            report_content.append("[No detailed output available or filtered]")
        report_content.append("-" * 30)

    report_text = "\n".join(report_content)

    report_filename = f"penai_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = os.path.join(output_dir, report_filename)
    try:
        with open(report_path, "w") as f:
            f.write(report_text)
        print(f"\n{Icons.SUCCESS} {Colors.GREEN}Report saved to: {report_path}{Colors.RESET}")
    except IOError as e:
        log_error(f"Failed to save report to {report_path}: {e}")

    print(f"\n{Colors.CYAN}--- Execution Summary ---{Colors.RESET}")
    
    if not command_results:
        print(f"{Icons.INFO} No commands were executed.")
        print("-" * 25)
        return

    table_data = []
    headers = ["Tool", "Status", "Return Code", "Log File (Snippet)"]
    
    col_widths = {header: len(header) for header in headers}
    
    for result in command_results:
        tool_display = result['tool']
        status_display_raw = result['status'].upper()
        return_code_display = str(result['returncode'])
        log_file_display = os.path.basename(result['log_file']) if result['log_file'] != "N/A" else "N/A"

        table_data.append([tool_display, status_display_raw, return_code_display, log_file_display])

        col_widths["Tool"] = max(col_widths["Tool"], len(tool_display))
        col_widths["Status"] = max(col_widths["Status"], len(status_display_raw))
        col_widths["Return Code"] = max(col_widths["Return Code"], len(return_code_display))
        col_widths["Log File (Snippet)"] = max(col_widths["Log File (Snippet)"], len(log_file_display))

    padding = 2
    for key in col_widths:
        col_widths[key] += padding

    def make_separator(widths):
        return "+" + "+".join(['-' * w for w in widths.values()]) + "+"

    def make_header_row(headers, widths):
        return "| " + " | ".join([h.ljust(widths[h]-padding) for h in headers]) + " |"

    def make_data_row(data, widths):
        tool_d, status_d_raw, rc_d, log_d = data
        
        status_color = Colors.GREEN if status_d_raw == 'SUCCESS' else \
                               Colors.RED if status_d_raw in ['FAILURE', 'ERROR', 'SKIPPED', 'TOOL_MISSING'] else \
                               Colors.YELLOW
        
        return (
            f"| {tool_d.ljust(widths['Tool']-padding)} | "
            f"{status_color}{status_d_raw.ljust(widths['Status']-padding)}{Colors.RESET} | "
            f"{rc_d.ljust(widths['Return Code']-padding)} | "
            f"{log_d.ljust(widths['Log File (Snippet)']-padding)} |"
        )

    header_separator = make_separator(col_widths)

    print(header_separator)
    print(make_header_row(headers, col_widths))
    print(header_separator)

    for row_data in table_data:
        print(make_data_row(row_data, col_widths))

    print(header_separator)
    print(f"{Icons.INFO} For full details, check logs in '{output_dir}' and the full report at {report_path}")

def execute_ai_commands(ai_response: str) -> bool:
    """Execute commands found in AI response"""
    commands = extract_commands(ai_response)
    if not commands:
        log_message("No executable commands found in AI response")
        return True

    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{Icons.INFO} {Colors.CYAN}The AI has suggested the following commands:{Colors.RESET}")
    for i, cmd in enumerate(commands):
        print(f"{Colors.GRAY}--- Command {i+1} ---{Colors.RESET}")
        print(f"{Colors.YELLOW}{cmd}{Colors.RESET}")
    print(f"{Colors.GRAY}-------------------{Colors.RESET}")

    proceed = input(f"{Icons.PROMPT} Do you want to execute these commands? (Y/n): ").strip().lower()
    if proceed not in ('', 'y', 'yes'):
        print(f"{Icons.INFO} {Colors.YELLOW}Command execution cancelled by user.{Colors.RESET}")
        return False

    all_commands_completed_successfully = True
    executed_command_results: List[Dict] = []

    for cmd_idx, cmd in enumerate(commands):
        if execution_interrupted_flag.is_set():
            print(f"\n{Icons.INFO} {Colors.YELLOW}Skipping remaining commands due to interruption.{Colors.RESET}")
            all_commands_completed_successfully = False
            break

        if not cmd.strip():
            continue

        formatted_cmd = cmd
        if target_ip_url:
            formatted_cmd = formatted_cmd.replace("<target_IP>", target_ip_url)
            formatted_cmd = formatted_cmd.replace("<TARGET_IP>", target_ip_url)
            formatted_cmd = formatted_cmd.replace("$TARGET", target_ip_url)

        # Determine the primary tool being run
        tool = "unknown_command"
        if formatted_cmd.startswith("sudo "):
            potential_tool_name = formatted_cmd.split()[1]
        else:
            potential_tool_name = formatted_cmd.split()[0]

        # Skip file creation commands
        if "cat <<" in formatted_cmd and "EOF" in formatted_cmd and ">" in formatted_cmd:
            tool = "file_creation_cat"
            # Execute file creation commands directly without prompting for installation
            print(f"{Icons.COMMAND} {Colors.PURPLE}Executing file creation:{Colors.RESET} {Colors.YELLOW}{formatted_cmd.splitlines()[0]}...{Colors.RESET}")
            try:
                subprocess.run(formatted_cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log_message(f"File created successfully: {formatted_cmd}")
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": 0,
                    "stdout": "File created successfully.", "stderr": "",
                    "log_file": "N/A", "status": "success"
                })
            except subprocess.CalledProcessError as e:
                log_error(f"File creation failed: {e}")
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": e.returncode,
                    "stdout": e.stdout, "stderr": e.stderr,
                    "log_file": "N/A", "status": "failure"
                })
                all_commands_completed_successfully = False
            continue
        elif re.match(r"echo\s+(['\"`].*?['\"`]\s*)?>\s*\S+", formatted_cmd):
            tool = "file_creation_echo"
            print(f"{Icons.COMMAND} {Colors.PURPLE}Executing file creation:{Colors.RESET} {Colors.YELLOW}{formatted_cmd.splitlines()[0]}...{Colors.RESET}")
            try:
                subprocess.run(formatted_cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log_message(f"File created successfully: {formatted_cmd}")
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": 0,
                    "stdout": "File created successfully.", "stderr": "",
                    "log_file": "N/A", "status": "success"
                })
            except subprocess.CalledProcessError as e:
                log_error(f"File creation failed: {e}")
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": e.returncode,
                    "stdout": e.stdout, "stderr": e.stderr,
                    "log_file": "N/A", "status": "failure"
                })
                all_commands_completed_successfully = False
            continue
        elif re.match(r"chmod\s+\+x\s+\S+", formatted_cmd):
            tool = "chmod"
            print(f"{Icons.COMMAND} {Colors.PURPLE}Executing chmod:{Colors.RESET} {Colors.YELLOW}{formatted_cmd}{Colors.RESET}")
            try:
                subprocess.run(formatted_cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log_message(f"Chmod executed successfully: {formatted_cmd}")
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": 0,
                    "stdout": "Chmod executed successfully.", "stderr": "",
                    "log_file": "N/A", "status": "success"
                })
            except subprocess.CalledProcessError as e:
                log_error(f"Chmod failed: {e}")
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": e.returncode,
                    "stdout": e.stdout, "stderr": e.stderr,
                    "log_file": "N/A", "status": "failure"
                })
                all_commands_completed_successfully = False
            continue
        elif potential_tool_name.endswith(".py") or potential_tool_name.endswith(".sh"):
            tool = os.path.basename(potential_tool_name)
        elif "python" in potential_tool_name or "python3" in potential_tool_name:
            if len(formatted_cmd.split()) > 1 and formatted_cmd.split()[1].endswith(".py"):
                tool = os.path.basename(formatted_cmd.split()[1])
            else:
                tool = "python_interpreter"
        else:
            tool = potential_tool_name.split('/')[-1]

        # Check if tool is available
        if not check_tool_installed(tool):
            print(f"{Icons.ERROR} {Colors.RED}Tool '{tool}' not found.{Colors.RESET}")
            if not install_tool_interactive(tool):
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": -1,
                    "stdout": "", "stderr": f"Tool '{tool}' not found and could not be installed.",
                    "log_file": "N/A", "status": "tool_missing"
                })
                all_commands_completed_successfully = False
                continue

        # Check for root requirements
        needs_root = ("sudo" in formatted_cmd or 
                     ("nmap" in formatted_cmd and any(flag in formatted_cmd for flag in ["-sS", "-O", "-sV"])))
        
        if needs_root and not check_root_privileges():
            print(f"{Icons.ROOT} {Colors.RED}Command requires root privileges:{Colors.RESET}")
            print(f"  {Colors.YELLOW}{formatted_cmd}{Colors.RESET}")
            choice = input(f"{Icons.PROMPT} Run with sudo? (Y/n): ").lower().strip()
            if choice in ('', 'y', 'yes'):
                if not formatted_cmd.startswith("sudo"):
                    formatted_cmd = f"sudo {formatted_cmd}"
            else:
                print(f"{Icons.INFO} Skipping root-required command: {formatted_cmd}")
                executed_command_results.append({
                    "tool": tool, "command": formatted_cmd, "returncode": -1,
                    "stdout": "", "stderr": "Skipped due to missing root privileges.",
                    "log_file": "N/A", "status": "skipped"
                })
                all_commands_completed_successfully = False
                continue

        # Prepare environment variables
        env = os.environ.copy()
        if target_ip_url:
            env["TARGET"] = target_ip_url

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_file_name = f"{tool}_{timestamp}.log"
        output_file_path = os.path.join(output_dir, output_file_name)
        
        print(f"{Icons.COMMAND} {Colors.PURPLE}Executing:{Colors.RESET} {Colors.YELLOW}{formatted_cmd}{Colors.RESET}")
        
        command_output_buffer = {"stdout": "", "stderr": "", "returncode": -999}
        cmd_runner_thread = Thread(target=run_single_command, 
                                   args=(formatted_cmd, env, command_output_buffer, tool))
        cmd_runner_thread.start()

        animation_thread = Thread(target=animate_thinking, args=(f"Running {tool}",))
        animation_stop_event.clear()
        animation_thread.start()

        while cmd_runner_thread.is_alive():
            if execution_interrupted_flag.is_set():
                log_message(f"Global interruption flag set for '{tool}'. Stopping command thread.")
                break
            time.sleep(0.1)
        
        cmd_runner_thread.join()
        animation_stop_event.set()
        animation_thread.join()

        returncode = command_output_buffer["returncode"]
        stdout = command_output_buffer["stdout"]
        stderr = command_output_buffer["stderr"]

        current_command_status = "success"
        if execution_interrupted_flag.is_set():
            current_command_status = "interrupted"
            all_commands_completed_successfully = False
            print(f"{Icons.WARNING} {Colors.YELLOW}Execution of '{tool}' interrupted by user.{Colors.RESET}")
        elif returncode == 0:
            print(f"{Icons.SUCCESS} {Colors.GREEN}Command '{tool}' completed successfully.{Colors.RESET} Full output logged to {output_file_name}")
            if verbose_mode:
                print(f"{Icons.OUTPUT} {Colors.CYAN}Summary (Verbose Mode):{Colors.RESET}")
                print(f"{Colors.GRAY}{process_tool_output(tool, stdout) if stdout else '[No filtered output]'}{Colors.RESET}")
        else:
            current_command_status = "failure"
            all_commands_completed_successfully = False
            print(f"{Icons.ERROR} {Colors.RED}Command '{tool}' failed (Exit Code: {returncode}).{Colors.RESET} Details logged to {output_file_name}")
            print(f"{Icons.OUTPUT} {Colors.RED}Error snippet (first 500 chars):{Colors.RESET}")
            print(f"{Colors.RED}{stderr[:500] if stderr else '[No error output]'}{Colors.RESET}")

        try:
            with open(output_file_path, "w") as f:
                f.write(f"Command: {formatted_cmd}\n")
                f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
                f.write(f"Return Code: {returncode}\n")
                f.write("\n--- STDOUT ---\n")
                f.write(stdout + "\n")
                f.write("\n--- STDERR ---\n")
                f.write(stderr + "\n")
            log_message(f"Command output saved to: {output_file_path}")
        except IOError as e:
            log_error(f"Could not write output to file {output_file_path}: {e}")
        
        executed_command_results.append({
            "tool": tool,
            "command": formatted_cmd,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "log_file": output_file_path,
            "status": current_command_status
        })
        
        if current_command_status == "interrupted":
            break

    generate_and_save_report(executed_command_results)
    
    return all_commands_completed_successfully

def send_to_openrouter(user_prompt: str) -> bool:
    """Send prompt to OpenRouter API"""
    global current_model

    system_info = f"OS: {platform.system()} {platform.release()} ({platform.machine()})"
    formatted_model_role = MODEL_ROLE_TEMPLATE.format(os_info=system_info)

    messages = [{"role": "system", "content": formatted_model_role}]
    messages.extend([{"role": "assistant" if msg["role"] == "model" else msg["role"], 
                      "content": msg["content"]} for msg in conversation_history])

    current_message_content = user_prompt
    if explanation_mode:
        current_message_content += "\n\n(Provide detailed explanations)"
    if target_ip_url:
        current_message_content += f"\n\n(Current target: '{target_ip_url}')"

    messages.append({"role": "user", "content": current_message_content})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "[https://github.com/your-repo-link-here](https://github.com/your-repo-link-here)",
        "X-Title": "PenAI"
    }

    animation_thread = Thread(target=animate_thinking, args=("AI is thinking",))
    animation_stop_event.clear()
    animation_thread.start()

    response_text = ""
    last_error = ""
    for model in OPENROUTER_MODELS:
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            response = requests.post(OPENROUTER_API_BASE, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            
            data = response.json()
            response_text = data['choices'][0]['message']['content']
            current_model = model
            break
        except requests.exceptions.RequestException as e:
            last_error = f"Request error with model {model}: {e}"
            log_error(last_error)
        except json.JSONDecodeError:
            last_error = f"Failed to decode JSON response from model {model}."
            log_error(last_error)
        except Exception as e:
            last_error = f"An unexpected error occurred with model {model}: {str(e)}"
            log_error(last_error)

    animation_stop_event.set()
    animation_thread.join()

    if not response_text:
        log_error(f"All models failed to respond. Last error: {last_error}")
        return False

    add_to_history("model", response_text)

    commands_found = extract_commands(response_text)

    if commands_found:
        print(f"\n{Colors.PURPLE}AI Response:{Colors.RESET}\n{remove_code_blocks(response_text)}\n") # Print the conversational part
        return execute_ai_commands(response_text)
    else:
        print(f"\n{Colors.PURPLE}AI Response:{Colors.RESET}\n{response_text}\n")
        return True
        
def main():
    """Main application entry point"""
    global target_ip_url, verbose_mode, explanation_mode, conversation_history
    
    if not OPENROUTER_API_KEY:
        log_error("OPENROUTER_API_KEY environment variable not set. Please set it to proceed.")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    setup_readline()

    clear_screen()
    print(get_random_banner())
    print(f"{Colors.CYAN}=== AI-Powered Cybersecurity Assistant ==={Colors.RESET}")
    print(f"{Icons.INFO} {Colors.GRAY}Type 'help' for available commands{Colors.RESET}")
    print_status()

    while True:
        try:
            user_input = input(f"{Icons.PROMPT} ").strip()
            
            if not user_input:
                continue
                
            command_parts = user_input.lower().split(maxsplit=1)
            main_command = command_parts[0]

            if main_command == "help":
                print(f"\n{Colors.CYAN}--- Available Commands ---{Colors.RESET}")
                print(f"{Icons.INFO} {Colors.GREEN}help:{Colors.RESET} Show this help message.")
                print(f"{Icons.INFO} {Colors.GREEN}exit:{Colors.RESET} Exit the application.")
                print(f"{Icons.INFO} {Colors.GREEN}clear:{Colors.RESET} Clear the terminal screen.")
                print(f"{Icons.INFO} {Colors.GREEN}status:{Colors.RESET} Display current configuration and status.")
                print(f"{Icons.INFO} {Colors.GREEN}set target <IP|URL>:{Colors.RESET} Set the target IP address or URL for actions (e.g., 'set target 192.168.1.1').")
                print(f"{Icons.INFO} {Colors.GREEN}unset target:{Colors.RESET} Clear the currently set target.")
                print(f"{Icons.INFO} {Colors.GREEN}verbose [on|off]:{Colors.RESET} Toggle verbose command output. Shows full stdout/stderr after execution. (Currently: {verbose_mode})")
                print(f"{Icons.INFO} {Colors.GREEN}explain [on|off]:{Colors.RESET} Toggle AI explanations for commands. (Currently: {explanation_mode})")
                print(f"{Icons.INFO} {Colors.GREEN}model [list|<model_name>]:{Colors.RESET} List available models or set a specific model.")
                print(f"{Icons.INFO} {Colors.GREEN}history:{Colors.RESET} Show the current conversation history with the AI.")
                print(f"{Icons.INFO} {Colors.GREEN}reset:{Colors.RESET} Clear the conversation history and reset settings.")
                print(f"\n{Icons.INFO} {Colors.GRAY}Any other input will be sent to the AI for processing.{Colors.RESET}\n")

            elif main_command == "exit":
                print(f"{Icons.INFO} {Colors.BLUE}Exiting PenAI. Goodbye!{Colors.RESET}")
                break

            elif main_command == "clear":
                clear_screen()
                print(get_random_banner())
                print(f"{Colors.CYAN}=== AI-Powered Cybersecurity Assistant ==={Colors.RESET}")
                print(f"{Icons.INFO} {Colors.GRAY}Type 'help' for available commands{Colors.RESET}")
                print_status()

            elif main_command == "status":
                print_status()

            elif main_command == "set":
                if len(command_parts) > 1 and command_parts[1].startswith("target "):
                    target_value = command_parts[1].split(" ", 1)[1].strip()
                    if target_value:
                        target_ip_url = target_value
                        print(f"{Icons.SUCCESS} {Colors.GREEN}Target set to: {target_ip_url}{Colors.RESET}")
                        add_to_history("system", f"Target set to {target_ip_url}")
                    else:
                        log_warning("Please provide a target IP address or URL.")
                else:
                    log_warning("Invalid 'set' command. Usage: 'set target <IP|URL>'")

            elif main_command == "unset":
                if len(command_parts) > 1 and command_parts[1] == "target":
                    if target_ip_url:
                        print(f"{Icons.SUCCESS} {Colors.GREEN}Target {target_ip_url} unset.{Colors.RESET}")
                        target_ip_url = ""
                        add_to_history("system", "Target unset.")
                    else:
                        print(f"{Icons.INFO} {Colors.GRAY}No target is currently set.{Colors.RESET}")
                else:
                    log_warning("Invalid 'unset' command. Usage: 'unset target'")

            elif main_command == "verbose":
                if len(command_parts) > 1:
                    toggle_value = command_parts[1].strip().lower()
                    if toggle_value == "on":
                        verbose_mode = True
                        print(f"{Icons.SUCCESS} {Colors.GREEN}Verbose command output is now ON.{Colors.RESET}")
                    elif toggle_value == "off":
                        verbose_mode = False
                        print(f"{Icons.SUCCESS} {Colors.GREEN}Verbose command output is now OFF.{Colors.RESET}")
                    else:
                        log_warning("Invalid usage. Use 'verbose on' or 'verbose off'.")
                else:
                    verbose_mode = not verbose_mode
                    print(f"{Icons.SUCCESS} {Colors.GREEN}Verbose command output is now {'ON' if verbose_mode else 'OFF'}.{Colors.RESET}")
                print_status()

            elif main_command == "explain":
                if len(command_parts) > 1:
                    toggle_value = command_parts[1].strip().lower()
                    if toggle_value == "on":
                        explanation_mode = True
                        print(f"{Icons.SUCCESS} {Colors.GREEN}AI explanations are now ON.{Colors.RESET}")
                    elif toggle_value == "off":
                        explanation_mode = False
                        print(f"{Icons.SUCCESS} {Colors.GREEN}AI explanations are now OFF.{Colors.RESET}")
                    else:
                        log_warning("Invalid usage. Use 'explain on' or 'explain off'.")
                else:
                    explanation_mode = not explanation_mode
                    print(f"{Icons.SUCCESS} {Colors.GREEN}AI explanations are now {'ON' if explanation_mode else 'OFF'}.{Colors.RESET}")
                print_status()

            elif main_command == "model":
                if len(command_parts) > 1:
                    sub_command = command_parts[1].strip().lower()
                    if sub_command == "list":
                        print(f"\n{Colors.CYAN}--- Available Models ---{Colors.RESET}")
                        for idx, model in enumerate(OPENROUTER_MODELS):
                            status = "(current)" if model == current_model else ""
                            print(f"{Colors.INFO} {idx + 1}. {model} {Colors.YELLOW}{status}{Colors.RESET}")
                        print("")
                    elif sub_command in OPENROUTER_MODELS:
                        current_model = sub_command
                        print(f"{Icons.SUCCESS} {Colors.GREEN}AI model set to: {current_model}{Colors.RESET}")
                        print_status()
                    else:
                        log_warning(f"Model '{sub_command}' not found. Use 'model list' to see available models.")
                else:
                    log_warning("Invalid 'model' command. Usage: 'model list' or 'model <model_name>'")

            elif main_command == "history":
                if not conversation_history:
                    print(f"{Icons.INFO} {Colors.GRAY}No conversation history yet.{Colors.RESET}")
                    continue
                print(f"\n{Colors.CYAN}--- Conversation History ---{Colors.RESET}")
                for msg in conversation_history:
                    role_color = Colors.BLUE if msg["role"] == "user" else Colors.PURPLE
                    role_display = "You" if msg["role"] == "user" else "AI"
                    # Only print full AI response if it's not commands
                    content_to_display = msg["content"]
                    if msg["role"] == "model" and extract_commands(content_to_display):
                        content_to_display = "[AI generated commands]"
                    
                    print(f"{role_color}{role_display}:{Colors.RESET} {content_to_display}")
                print("-" * 28 + "\n")

            elif main_command == "reset":
                confirm = input(f"{Icons.WARNING} {Colors.YELLOW}Are you sure you want to clear all conversation history and reset settings (target, verbose, explain)? (y/N): {Colors.RESET}").strip().lower()
                if confirm == 'y':
                    conversation_history = []
                    target_ip_url = ""
                    verbose_mode = False
                    explanation_mode = False
                    print(f"{Icons.SUCCESS} {Colors.GREEN}PenAI has been reset.{Colors.RESET}")
                    print_status()
                else:
                    print(f"{Icons.INFO} {Colors.GRAY}Reset cancelled.{Colors.RESET}")

            else:
                add_to_history("user", user_input)
                send_to_openrouter(user_input)

        except KeyboardInterrupt:
            print(f"\n{Icons.INFO} {Colors.YELLOW}Operation interrupted by user. Type 'exit' to quit or continue.{Colors.RESET}")
            execution_interrupted_flag.set() # Set the flag to stop any running threads
            animation_stop_event.set() # Stop any thinking animation
            # Give a moment for threads to clean up
            time.sleep(0.2)
            execution_interrupted_flag.clear() # Clear for next command
            animation_stop_event.clear() # Clear for next animation
            continue
        except Exception as e:
            log_error(f"An unhandled error occurred: {e}")
            log_message(f"Traceback: {sys.exc_info()[2]}")
            continue

if __name__ == "__main__":
    main()
