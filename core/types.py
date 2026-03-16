from typing import TypedDict, List

class Task(TypedDict):
    agent: str           # "explorer" or "coder"
    instruction: str     # what to do
    context: str         # filled by dispatcher with previous results

class TaskResult(TypedDict):
    task: Task           # the original task
    output: str          # what the agent produced
    success: bool        # did it work or not

class Message(TypedDict):
    role: str            # "user" or "assistant"
    content: str         # the message text
    timestamp: str       # when it was sent

class Plan(TypedDict):
    steps: List[Task]    # ordered list of tasks to execute