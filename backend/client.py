import asyncclick as click
import asyncio
import base64
import os
import urllib
from uuid import uuid4

from A2AServer.common.client import A2AClient, A2ACardResolver
from A2AServer.common.A2Atypes import TaskState, Task, TextPart, FilePart, FileContent
from A2AServer.common.utils.push_notification_auth import PushNotificationReceiverAuth


@click.command()
@click.option("--agent", default="http://localhost:10004")
@click.option("--session", default=0)
@click.option("--history", default=False)
async def cli(agent, session, history):
    card_resolver = A2ACardResolver(agent)
    card = card_resolver.get_agent_card()

    print("======= Agent Card ========")
    print(card.model_dump_json(exclude_none=True))

    client = A2AClient(agent_card=card)
    if session == 0:
        sessionId = uuid4().hex
    else:
        sessionId = session

    continue_loop = True
    streaming = card.capabilities.streaming

    while continue_loop:
        taskId = uuid4().hex
        print("=========  starting a new task ======== ")
        continue_loop = await completeTask(client, streaming, taskId, sessionId)

        if history and continue_loop:
            print("========= history ======== ")
            task_response = await client.get_task({"id": taskId, "historyLength": 10})
            print(task_response.model_dump_json(include={"result": {"history": True}}))


async def completeTask(client: A2AClient, streaming, taskId, sessionId):
    prompt = click.prompt(
        "\nWhat do you want to send to the agent? (:q or quit to exit)"
    )
    if prompt == ":q" or prompt == "quit":
        return False

    message = {
        "role": "user",
        "parts": [
            {
                "type": "text",
                "text": prompt,
            }
        ]
    }

    file_path = click.prompt(
        "Select a file path to attach? (press enter to skip)",
        default="",
        show_default=False,
    )
    if file_path and file_path.strip() != "":
        with open(file_path, "rb") as f:
            file_content = base64.b64encode(f.read()).decode('utf-8')
            file_name = os.path.basename(file_path)

        message["parts"].append(
            {
                "type": "file",
                "file": {
                    "name": file_name,
                    "bytes": file_content,
                }
            }
        )

    payload = {
        "id": taskId,
        "sessionId": sessionId,
        "acceptedOutputModes": ["text"],
        "message": message,
    }

    taskResult = None
    if streaming:
        response_stream = client.send_task_streaming(payload)
        async for result in response_stream:
            print(f"stream event => {result.model_dump_json(exclude_none=True)}")
        taskResult = await client.get_task({"id": taskId})
    else:
        taskResult = await client.send_task(payload)
        print(f"\n{taskResult.model_dump_json(exclude_none=True)}")

    ## if the result is that more input is required, loop again.
    state = TaskState(taskResult.result.status.state)
    if state.name == TaskState.INPUT_REQUIRED.name:
        return await completeTask(
            client,
            streaming,
            taskId,
            sessionId
        )
    else:
        ## task is complete
        return True


if __name__ == "__main__":
    asyncio.run(cli())
