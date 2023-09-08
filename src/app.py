
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from queue import Empty, Queue
from threading import Thread
inputmsg = ["自上次重開機後所有客戶問的問題"]

import gradio as gr
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.chat_models import ChatOpenAI
from langchain.prompts import HumanMessagePromptTemplate
from langchain.schema import AIMessage, BaseMessage, HumanMessage, SystemMessage

from callback import QueueCallback

#MODELS_NAMES = ["gpt-3.5-turbo", "gpt-4"]
MODELS_NAMES = ["gpt-3.5-turbo"]
DEFAULT_TEMPERATURE = 0.7

ChatHistory = List[str]
# 定义一个新的函数，用于处理点击"显示所有问题"按钮的事件
def show_all_questions():
    return '\n'.join(inputmsg)
	
logging.basicConfig(
    format="[%(asctime)s %(levelname)s]: %(message)s", level=logging.INFO
)
# load up our system prompt
default_system_prompt = Path("prompts/system.prompt").read_text()
# for the human, we will just inject the text
human_message_prompt_template = HumanMessagePromptTemplate.from_template("{text}")


def on_message_button_click(
    chat: Optional[ChatOpenAI],
    message: str,
    chatbot_messages: ChatHistory,
    messages: List[BaseMessage],
) -> Tuple[ChatOpenAI, str, ChatHistory, List[BaseMessage]]:
    if chat is None:
        # in the queue we will store our streamed tokens
        queue = Queue()
        # let's create our default chat
        chat = ChatOpenAI(
            model_name=MODELS_NAMES[0],
            temperature=DEFAULT_TEMPERATURE,
            streaming=True,
            callbacks=([QueueCallback(queue)]),
        )
    else:
        # hacky way to get the queue back
        queue = chat.callbacks[0].queue

    job_done = object()

    logging.info(f"Asking question to GPT, messages={messages}")
    # let's add the messages to our stuff
    messages.append(HumanMessage(content=message))
	#新增加入inputmsg
    inputmsg.append(message)
    chatbot_messages.append((message, ""))
    # this is a little wrapper we need cuz we have to add the job_done
    def task():
        chat(messages)
        queue.put(job_done)

    # now let's start a thread and run the generation inside it
    t = Thread(target=task)
    t.start()
    # this will hold the content as we generate
    content = ""
    # now, we read the next_token from queue and do what it has to be done
    while True:
        try:
            next_token = queue.get(True, timeout=1)
            if next_token is job_done:
                break
            content += next_token
            chatbot_messages[-1] = (message, content)
            yield chat, "", chatbot_messages, messages
        except Empty:
            continue
    # finally we can add our reply to messsages
    messages.append(AIMessage(content=content))
    logging.debug(f"reply = {content}")
    logging.info(f"Done!")
    return chat, "", chatbot_messages, messages


def system_prompt_handler(value: str) -> str:
    return value


def on_clear_button_click(system_prompt: str) -> Tuple[str, List, List]:
    return "", [], [SystemMessage(content=system_prompt)]


def on_apply_settings_button_click(
    system_prompt: str, model_name: str, temperature: float
):
    logging.info(
        f"Applying settings: model_name={model_name}, temperature={temperature}"
    )
    chat = ChatOpenAI(
        model_name=model_name,
        temperature=temperature,
        streaming=True,
        callbacks=[QueueCallback(Queue())],
    )
    # don't forget to nuke our queue
    chat.callbacks[0].queue.empty()
    return chat, *on_clear_button_click(system_prompt)


# some css why not, "borrowed" from https://huggingface.co/spaces/ysharma/Gradio-demo-streaming/blob/main/app.py
with gr.Blocks(
    css="""#col_container {width: 700px; margin-left: auto; margin-right: auto;}
                #chatbot {height: 400px; overflow: auto;}""",title="可以用自己資料回答的gpt"
) as demo:
    system_prompt = gr.State(default_system_prompt)
    # here we keep our state so multiple user can use the app at the same time!
    messages = gr.State([SystemMessage(content=default_system_prompt)])
    # same thing for the chat, we want one chat per use so callbacks are unique I guess
    chat = gr.State(None)
    
    with gr.Column(elem_id="col_container"):
        gr.Markdown("# 歡迎使用可以用自己資料回答的GPT! 🌟🚀")
        gr.Markdown(
            "可以設定GPT的角色及要回答的問題範圍太資料不要超過1000字GPT 3.5有限制"
        )
        with gr.Column():
            system_prompt_area = gr.TextArea(
                default_system_prompt, lines=4, label="個人化指令及希望回答的範圍", interactive=True
            )
            # we store the value into the state to avoid re rendering of the area
            system_prompt_area.input(
                system_prompt_handler,
                inputs=[system_prompt_area],
                outputs=[system_prompt],
            )
            system_prompt_button = gr.Button("設定")
           
          

        chatbot = gr.Chatbot()
        with gr.Column():
            message = gr.Textbox(label="輸入的問題")
            message.submit(
                on_message_button_click,
                [chat, message, chatbot, messages],
                [chat, message, chatbot, messages],
                queue=True,
            )
            message_button = gr.Button("送出", variant="primary")
            message_button.click(
                on_message_button_click,
                [chat, message, chatbot, messages],
                [chat, message, chatbot, messages],
            )
        with gr.Row():
            with gr.Column():
                clear_button = gr.Button("清除")
                clear_button.click(
                    on_clear_button_click,
                    [system_prompt],
                    [message, chatbot, messages],
                    queue=False,
                )
            with gr.Accordion("參數設定", open=False):
                model_name = gr.Dropdown(
                    choices=MODELS_NAMES, value=MODELS_NAMES[0], label="model"
                )
                temperature = gr.Slider(
                    minimum=0.0,
                    maximum=1.0,
                    value=0.7,
                    step=0.1,
                    label="變化度數值小回答一致性高",
                    interactive=True,
                )
                apply_settings_button = gr.Button("套用")
                apply_settings_button.click(
                    on_apply_settings_button_click,
                    [system_prompt, model_name, temperature],
                    [chat, message, chatbot, messages],
                )

        system_prompt_button.click(
            on_apply_settings_button_click,
            [system_prompt, model_name, temperature],
            [chat, message, chatbot, messages],
        )
        with gr.Row():
            show_questions_btn = gr.Button("顯示問過的問題")
            show_questions_output = gr.TextArea(label="所有問題")
            show_questions_btn.click(show_all_questions, outputs=[show_questions_output])

demo.queue()
demo.launch(share=True,server_name="0.0.0.0")
