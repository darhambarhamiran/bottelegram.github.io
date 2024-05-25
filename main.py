
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import logging

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
conn = sqlite3.connect('tictactoe.db', check_same_thread=False)
cursor = conn.cursor()

# Create games and waiting tables
cursor.execute('DROP TABLE IF EXISTS games')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS games (
        chat_id INTEGER PRIMARY KEY,
        board TEXT,
        current_player TEXT,
        player_x INTEGER,
        player_o INTEGER,
        msg_id_x INTEGER,
        msg_id_o INTEGER
    )
''')
cursor.execute('DROP TABLE IF EXISTS waiting')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS waiting (
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER
    )
''')
conn.commit()

# Define the player symbols
player_symbols = {
    "X": "❌",
    "O": "⭕"
}

# Initialize the game board
def init_board():
    return [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]

# Convert board to string for database storage
def board_to_str(board):
    return ''.join([''.join(row) for row in board])

# Convert string to board for gameplay
def str_to_board(board_str):
    return [list(board_str[i:i+3]) for i in range(0, len(board_str), 3)]

# Generate the game board as an InlineKeyboardMarkup
def generate_board_markup(board, chat_id):
    keyboard = [
        [InlineKeyboardButton(board[row][col], callback_data=f"{chat_id},{row},{col}") for col in range(3)] for row in range(3)
    ]
    return InlineKeyboardMarkup(keyboard)

# Define a function to start the game
def start_game(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id

    cursor.execute('SELECT * FROM games WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()

    if result:
        update.message.reply_text("بازی در حال حاضر در این چت فعال است. منتظر بمانید تا حریف پیدا شود یا بازی در حال انجام را ادامه دهید.")
        return

    cursor.execute('SELECT * FROM waiting WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        update.message.reply_text("شما قبلاً در صف انتظار برای حریف هستید.")
        return

    cursor.execute('INSERT INTO waiting (user_id, chat_id) VALUES (?, ?)', (user_id, chat_id))
    conn.commit()

    cursor.execute('SELECT * FROM waiting')
    waiting_players = cursor.fetchall()

    if len(waiting_players) >= 2:
        player_x = waiting_players[0]
        player_o = waiting_players[1]

        cursor.execute('DELETE FROM waiting WHERE user_id = ?', (player_x[0],))
        cursor.execute('DELETE FROM waiting WHERE user_id = ?', (player_o[0],))

        cursor.execute('INSERT INTO games (chat_id, board, current_player, player_x, player_o) VALUES (?, ?, ?, ?, ?)',
                       (chat_id, board_to_str(init_board()), "X", player_x[0], player_o[0]))
        conn.commit()

        context.bot.send_message(player_x[1], "حریف پیدا شد! شما بازیکن X هستید.")
        context.bot.send_message(player_o[1], "حریف پیدا شد! شما بازیکن O هستید.")

        cursor.execute('SELECT board FROM games WHERE chat_id = ?', (chat_id,))
        board_str = cursor.fetchone()[0]
        board = str_to_board(board_str)
        reply_markup = generate_board_markup(board, chat_id)

        msg_x = context.bot.send_message(player_x[1], "بازی شروع می‌شود. شما اولین بازیکن هستید.", reply_markup=reply_markup)
        msg_o = context.bot.send_message(player_o[1], "بازی شروع می‌شود. منتظر حرکت بازیکن X باشید.", reply_markup=reply_markup)

        cursor.execute('UPDATE games SET msg_id_x = ?, msg_id_o = ? WHERE chat_id = ?',
                       (msg_x.message_id, msg_o.message_id, chat_id))
        conn.commit()
    else:
        update.message.reply_text("در حال پیدا کردن حریف... منتظر بمانید.")

# Define a function to handle user moves
def handle_move(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data.split(",")
    chat_id = int(data[0])
    row, col = int(data[1]), int(data[2])
    user_id = query.from_user.id

    cursor.execute('SELECT board, current_player, player_x, player_o, msg_id_x, msg_id_o FROM games WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()

    if result:
        board_str, current_player, player_x, player_o, msg_id_x, msg_id_o = result
        board = str_to_board(board_str)

        if (current_player == "X" and user_id == player_x) or (current_player == "O" and user_id == player_o):
            if board[row][col] == " ":
                board[row][col] = current_player
                next_player = "O" if current_player == "X" else "X"

                cursor.execute('UPDATE games SET board = ?, current_player = ? WHERE chat_id = ?',
                               (board_to_str(board), next_player, chat_id))
                conn.commit()

                reply_markup = generate_board_markup(board, chat_id)

                # Update the message for both players
                context.bot.edit_message_reply_markup(chat_id=player_x, message_id=msg_id_x, reply_markup=reply_markup)
                context.bot.edit_message_reply_markup(chat_id=player_o, message_id=msg_id_o, reply_markup=reply_markup)

                if check_winner(board):
                    win_message = f"بازیکن {player_symbols[current_player]} برنده شد!"
                    context.bot.send_message(player_x, win_message)
                    context.bot.send_message(player_o, win_message)
                    cursor.execute('DELETE FROM games WHERE chat_id = ?', (chat_id,))
                    conn.commit()
                elif check_draw(board):
                    draw_message = "بازی مساوی شد!"
                    context.bot.send_message(player_x, draw_message)
                    context.bot.send_message(player_o, draw_message)
                    cursor.execute('DELETE FROM games WHERE chat_id = ?', (chat_id,))
                    conn.commit()
            else:
                query.answer("این خانه قبلاً انتخاب شده است. لطفاً خانه دیگری را انتخاب کنید.")
        else:
            query.answer("نوبت شما نیست.")
    else:
        query.answer("بازی پیدا نشد. لطفاً با دستور /start یک بازی جدید شروع کنید.")

def check_winner(board):
    for row in board:
        if row[0] == row[1] == row[2] != " ":
            return True
    for col in range(3):
        if board[0][col] == board[1][col] == board[2][col] != " ":
            return True
    if board[0][0] == board[1][1] == board[2][2] != " ":
        return True
    if board[0][2] == board[1][1] == board[2][0] != " ":
        return True
    return False

def check_draw(board):
    for row in board:
        if " " in row:
            return False
    return True

def reset_game(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    cursor.execute('DELETE FROM games WHERE chat_id = ?', (chat_id,))
    cursor.execute('DELETE FROM waiting WHERE chat_id = ?', (chat_id,))
    conn.commit()
    update.message.reply_text("بازی ریست شد. با استفاده از دستور /start بازی جدیدی شروع کنید.")

# Set up the updater and dispatcher
updater = Updater("7079782220:AAF4JFSU4CJxj2wCjccCbfWqQRiA_1hT94g", use_context=True)
dispatcher = updater.dispatcher

# Register handlers for commands and callback queries
dispatcher.add_handler(CommandHandler("start", start_game))
dispatcher.add_handler(CallbackQueryHandler(handle_move))
dispatcher.add_handler(CommandHandler("reset", reset_game))

# Start the bot
updater.start_polling()
updater.idle()