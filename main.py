from dotenv import load_dotenv
import os
import telebot
from telebot import types
from flask import Flask, request
import uuid
import re
import logging
from datetime import datetime

# 加载 .env 文件
load_dotenv()

API_TOKEN = os.getenv('API_TOKEN')
# 频道用户名
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')
bot = telebot.TeleBot(API_TOKEN)
# 获取频道信息并输出频道ID
channel_info = bot.get_chat(CHANNEL_USERNAME)

# 审稿群的chat ID
REVIEW_GROUP_ID = int(os.getenv('REVIEW_GROUP_ID'))
# 公开频道ID
PUBLISH_CHANNEL_ID = channel_info.id

# 用于存储投稿内容的字典
submissions = {}
# 投稿人
users = {}

# 设置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # 你的 Webhook URL
app = Flask(__name__)

# 预定义的投稿模板
SUBMISSION_TEMPLATE = """
请使用以下模板进行投稿：

昵称：
性别：
年龄：
身高：
体重：
性格：
爱好：
性癖：
雷区：
在线时间：
想找的人：
联系方式：
"""

# 正则表达式匹配投稿格式
SUBMISSION_PATTERN = (
    r'^昵称：.*\n'
    r'性别：.*\n'
    r'年龄：.*\n'
    r'身高：.*\n'
    r'体重：.*\n'
    r'性格：.*\n'
    r'爱好：.*\n'
    r'性癖：.*\n'
    r'雷区：.*\n'
    r'在线时间：.*\n'
    r'想找的人：.*\n'
    r'联系方式：.*$'
)

WELCOME_TEXT = """
欢迎使用本投稿机器人，您可以使用如下命令：

/submit - 使用这个命令可以开始投稿
/template - 使用这个命令可以获取投稿模板

Tip1：投稿时请按照模板格式来编写稿件
Tip2: 如果您未设置TG账号的用户名，建议您在联系方式留下其他联系方式，否则对方无法联系上您，这个很重要
"""


# 用户名格式化
def user_format(user):
    first_name = user.first_name if user.first_name else ""
    last_name = user.last_name if user.last_name else ""
    username = user.username if user.username else "未知用户"
    return f"{first_name} {last_name}(@{username})"


# 定义投稿命令的处理函数
@bot.message_handler(commands=['submit'])
def handle_submit(message):
    # 发送欢迎消息并要求用户输入投稿内容
    msg = bot.reply_to(message, "请输入你的投稿内容：")
    bot.register_next_step_handler(msg, receive_submission)


def receive_submission(message):
    submission = message.text
    user = message.from_user

    # 校验投稿内容是否符合格式
    if not re.match(SUBMISSION_PATTERN, submission, re.MULTILINE):
        msg = bot.reply_to(message, f"格式不正确，请按照以下模板提交：\n{SUBMISSION_TEMPLATE}")
        bot.register_next_step_handler(msg, receive_submission)
        return

    # 生成唯一标识符并存储投稿内容
    submission_id = str(uuid.uuid4())
    submissions[submission_id] = submission
    users[submission_id] = user

    # 创建审核按钮，并将投稿内容编码到回调数据中
    markup = types.InlineKeyboardMarkup()
    approve_button = types.InlineKeyboardButton("通过", callback_data=f"approve|{submission_id}")
    reject_button = types.InlineKeyboardButton("不通过", callback_data=f"reject|{submission_id}")
    markup.add(approve_button, reject_button)
    format_username = user_format(user)
    # 发送投稿内容到审稿群
    bot.send_message(REVIEW_GROUP_ID,
                     f"新投稿来自 {format_username}:\n\n{submission}",
                     reply_markup=markup)

    # 给用户回复确认消息
    bot.reply_to(message, "感谢你的投稿！管理员会尽快审核。")


# 处理审核按钮点击
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve|") or call.data.startswith("reject|"))
def handle_review(call):
    status_text = ""
    try:
        action, submission_id = call.data.split("|", 1)  # 提取投稿 ID
        # 根据投稿 ID 获取投稿内容
        submission_text = submissions.get(submission_id, "投稿内容未找到")
        user = users.get(submission_id)
        format_username = user_format(user)
        reviewer = call.from_user
        reviewer_name = reviewer.first_name if reviewer.first_name else ""
        reviewer_name += f" {reviewer.last_name}" if reviewer.last_name else ""
        review_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if action == "approve":
            status_text = f"✅ **投稿已通过**\n\n审核人: {reviewer_name}\n审核时间: {review_time}"
            bot.answer_callback_query(call.id, status_text)
            # bot.send_message(call.message.chat.id, f"{status_text}")
            # 在发送到频道的信息下方添加按钮
            markup = types.InlineKeyboardMarkup()
            post_button = types.InlineKeyboardButton("我要投稿", url="https://t.me/wenaitougao_bot")
            group_button = types.InlineKeyboardButton("交友聊天", url="https://t.me/typel0ve")
            markup.add(post_button, group_button)
            # 将通过的投稿内容发送到发布群
            bot.send_message(PUBLISH_CHANNEL_ID,
                             f"来自{format_username}的投稿:\n\n{submission_text}",
                             reply_markup=markup)
        elif action == "reject":
            status_text = f"❌ **投稿未通过**\n\n审核人: {reviewer_name}\n审核时间: {review_time}"
            bot.answer_callback_query(call.id, status_text)
            # bot.send_message(call.message.chat.id, f"{status_text}")

        # 编辑原消息，移除按钮，并添加审核状态
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text=f"{call.message.text}\n\n{status_text}", parse_mode='Markdown')
        # 审核完成后删除投稿内容
        submissions.pop(submission_id, None)
        users.pop(submission_id, None)
    except ValueError as e:
        bot.answer_callback_query(call.id, "处理投稿时出错")
        print(f"Error processing callback data: {call.data} - {str(e)}")


# 处理获取模板命令
@bot.message_handler(commands=['template'])
def handle_template(message):
    bot.send_message(message.chat.id, SUBMISSION_TEMPLATE)


# 处理其他文本消息
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, WELCOME_TEXT)


# 处理所有文本消息
# @bot.message_handler(func=lambda message: True)
# def send_chat_id(message):
#     chat_id = message.chat.id
#     bot.reply_to(message, f"Your chat ID is {chat_id}")


@app.route('/' + API_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '!', 200


@app.route('/')
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + API_TOKEN)
    return 'Webhook set!', 200


@app.route('/set_webhook')
def set_webhook():
    webhook_url = WEBHOOK_URL + API_TOKEN
    s = bot.set_webhook(url=webhook_url)
    if s:
        return "Webhook setup ok"
    else:
        return "Webhook setup failed"


@app.route('/health')
def health_check():
    return 'OK', 200


if __name__ == "__main__":
    try:
        logger.info("Starting Flask server...")
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
    except Exception as e:
        logger.error(f"Error starting the server: {e}")
