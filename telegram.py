import asyncio
loop = asyncio.get_event_loop()
import aiohttp
import async_timeout
import datetime

class TelegramAPIError(Exception):
    pass

class UpdateError(Exception):
    pass

class Bot:
    def __init__(self, token):
        self.token = token
        self.user_data = None
        self.updates = list()
        self.chats = list()
        self.commands = dict()
        self.offset = 0
        # Update user_data
        loop.create_task(self.update_bot_data())

    def __repr__(self):
        return f"<Bot {self.user_data.first_name}>"

    def __hash__(self):
        return hash(self.token)

    async def update_bot_data(self):
        """Update self.user_data with the latest information from /getMe."""
        data = await self.api_request("getMe")
        self.user_data = User(data)

    async def get_updates(self):
        """Get the latest updates from the Telegram API with /getUpdates."""
        try:
            data = await self.api_request("getUpdates", offset=self.offset, timeout=300)
        except asyncio.TimeoutError:
            return
        for update in data:
            try:
                self.updates.append(Update(update))
            except NotImplementedError:
                pass
        if len(data) > 0:
            self.offset = self.updates[-1].update_id + 1

    async def parse_update(self, update):
        """Parse the first update in the list."""
        # Add the chat to the chat list
        if update.message.chat not in self.chats:
            self.chats.append(update.message.chat)
        # Add the user to the chat
        chat = self.find_chat(update.message.chat.chat_id)
        if update.message.sent_from not in chat.users:
            chat.users.append(update.message.sent_from)
        # Add / edit the message to the message list
        if not update.message.edited:
            chat.messages.append(update.message)
        else:
            try:
                i = chat.messages.index(chat.find_message(update.message.msg_id))
            except ValueError:
                pass
            else:
                chat.messages[i] = update.message
        # Check if a command can be run
        # TODO: use message entities?
        if isinstance(update.message.content, str) and update.message.content.startswith("/"):
            command = update.message.content.split(" ")[0].lstrip("/")
            if command in self.commands:
                self.commands[command](self, update)

    def find_update(self, upd_id):
        for update in self.updates:
            if update.update_id == upd_id:
                return update

    def find_chat(self, chat_id):
        for chat in self.chats:
            if chat.chat_id == chat_id:
                return chat

    async def api_request(self, endpoint, **params):
        """Send a request to the Telegram API at the specified endpoint."""
        # Request timeout is 10 seconds.
        with async_timeout.timeout(10):
            # Create a new session for each request.
            async with aiohttp.ClientSession() as session:
                # Send the request to the Telegram API
                token = self.token
                async with session.request("GET", f"https://api.telegram.org/bot{token}/{endpoint}", params=params) as response:
                    # Check for errors in the request
                    if response.status != 200:
                        raise TelegramAPIError(f"Request returned {response.status} {response.reason}")
                    # Parse the json data as soon it's ready
                    data = await response.json()
                    # Check for errors in the response
                    if not data["ok"]:
                        error = data["description"]
                        raise TelegramAPIError(f"Response returned an error: {error}")
                    # Return a dictionary containing the data
                    return data["result"]


class Update:
    def __init__(self, upd_dict):
        self.update_id = upd_dict["update_id"]
        if "message" in upd_dict:
            self.message = Message(upd_dict["message"])
        elif "edited_message" in upd_dict:
            self.message = Message(upd_dict["edited_message"], edited=True)
        elif "channel_post" in upd_dict:
            self.message = Message(upd_dict["channel_post"])
        elif "edited_channel_post" in upd_dict:
            self.message = Message(upd_dict["edited_channel_post"], edited=True)
        else:
            raise NotImplementedError("No inline support yet.")


class Chat:
    def __init__(self, chat_dict):
        self.chat_id = chat_dict["id"]
        self.type = chat_dict["type"]
        self.users = list()
        self.admins = list()
        self.messages = list()
        self.chat_photo = None
        if self.type == "private":
            self.first_name = chat_dict["first_name"]
            if "last_name" in chat_dict:
                self.last_name = chat_dict["last_name"]
            else:
                self.last_name = None
            if "username" in chat_dict:
                self.username = chat_dict["username"]
            else:
                self.username = None
            self.title = f"{self.first_name} {self.last_name}"
            self.everyone_is_admin = True
        elif self.type == "group" or self.type == "supergroup" or self.type == "channel":
            self.first_name = None
            self.last_name = None
            if self.type == "supergroup" or self.type == "channel":
                self.everyone_is_admin = False
                if "username" in chat_dict:
                    self.username = chat_dict["username"]
                else:
                    self.username = None
            else:
                self.everyone_is_admin = chat_dict["all_members_are_administrators"]
                self.username = None
            self.title = chat_dict["title"]
        else:
            raise UpdateError(f"Unknown message type: {self.type}")

    def __repr__(self):
        return f"<{self.type} Chat {self.title}>"

    def __hash__(self):
        return self.chat_id

    def __eq__(self, other):
        if isinstance(other, Chat):
            return self.chat_id == other.chat_id
        else:
            TypeError("Can't compare Chat to a different object.")

    def find_message(self, msg_id):
        for msg in self.messages:
            if msg.msg_id == msg_id:
                return msg



class User:
    def __init__(self, user_dict):
        self.user_id = user_dict["id"]
        self.first_name = user_dict["first_name"]
        if "last_name" in user_dict:
            self.last_name = user_dict["last_name"]
        else:
            self.last_name = None
        if "username" in user_dict:
            self.username = user_dict["username"]
        else:
            self.username = None

    def __repr__(self):
        if self.username is not None:
            return f"<User {self.username}>"
        else:
            return f"<User {self.user_id}>"

    def __hash__(self):
        return self.user_id

    def __eq__(self, other):
        if isinstance(other, User):
            return self.user_id == other.user_id
        else:
            TypeError("Can't compare User to a different object.")


class Message:
    def __init__(self, msg_dict, edited=False):
        self.msg_id = msg_dict["message_id"]
        self.date = datetime.datetime.fromtimestamp(msg_dict["date"])
        self.chat = Chat(msg_dict["chat"])
        self.edited = edited
        if "from" in msg_dict:
            self.sent_from = User(msg_dict["from"])
        else:
            self.sent_from = None
        self.forwarded = "forward_date" in msg_dict
        if self.forwarded:
            if "forward_from" in msg_dict:
                self.original_sender = User(msg_dict["forward_from"])
            elif "forward_from_chat" in msg_dict:
                self.original_sender = Chat(msg_dict["forward_from_chat"])
                # TODO: Add forward_from_message_id
        if "reply_to_message" in msg_dict:
            self.is_reply_to = Message(msg_dict["reply_to_message"])
        else:
            self.is_reply_to = None
        if "text" in msg_dict:
            self.content = msg_dict["text"]
            # TODO: Check for MessageEntities
        elif "audio" in msg_dict:
            self.content = Audio(msg_dict["audio"])
        elif "document" in msg_dict:
            self.content = Document(msg_dict["document"])
        elif "game" in msg_dict:
            self.content = Game(msg_dict["game"])
        elif "photo" in msg_dict:
            self.content = Photo(msg_dict["photo"])
        elif "sticker" in msg_dict:
            self.content = Sticker(msg_dict["sticker"])
        elif "video" in msg_dict:
            self.content = Video(msg_dict["video"])
        elif "voice" in msg_dict:
            self.content = Voice(msg_dict["voice"])
        elif "contact" in msg_dict:
            self.content = Contact(msg_dict["contact"])
        elif "location" in msg_dict:
            self.content = Location(msg_dict["location"])
        elif "venue" in msg_dict:
            self.content = Venue(msg_dict["venue"])
        elif "new_chat_member" in msg_dict:
            self.content = ServiceMessage("new_chat_member", User(msg_dict["new_chat_member"]))
        elif "left_chat_member" in msg_dict:
            self.content = ServiceMessage("left_chat_member", User(msg_dict["left_chat_member"]))
        elif "new_chat_title" in msg_dict:
            self.content = ServiceMessage("new_chat_title", msg_dict["new_chat_title"])
        elif "new_chat_photo" in msg_dict:
            self.content = ServiceMessage("new_chat_photo", Photo(msg_dict["new_chat_photo"]))
        elif "delete_chat_photo" in msg_dict:
            self.content = ServiceMessage("delete_chat_photo")
        elif "group_chat_created" in msg_dict:
            self.content = ServiceMessage("group_chat_created")
        elif "supergroup_chat_created" in msg_dict:
            self.content = ServiceMessage("supergroup_chat_created")
        elif "channel_chat_created" in msg_dict:
            self.content = ServiceMessage("channel_chat_created")
        elif "migrate_to_chat_id" in msg_dict:
            self.content = ServiceMessage("migrate_to_chat_id", msg_dict["migrate_to_chat_id"])
        elif "migrate_from_chat_id" in msg_dict:
            self.content = ServiceMessage("migrate_from_chat_id", msg_dict["migrate_from_chat_id"])
        elif "pinned_message" in msg_dict:
            self.content = ServiceMessage("pinned_message", Message(msg_dict["pinned_message"]))
        else:
            raise UpdateError("Message doesn't contain anything.")

    def __repr__(self):
        if isinstance(self.content, str):
            return f"<Message: {self.content}>"
        else:
            return f"<Message containing {type(self.content)}>"


class ServiceMessage:
    def __init__(self, msg_type, extra=None):
        self.type = msg_type
        self.content = extra


class Audio:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Document:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Game:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Photo:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Sticker:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Video:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Voice:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Contact:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Location:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


class Venue:
    def __init__(self, init_dict):
        raise NotImplementedError("Not yet.")


def legoflegend(bot, update):
    print("Message received: " + repr(update))

b = Bot("ciao ruozi ciao ciao")
b.commands["lol"] = legoflegend
while True:
    loop.run_until_complete(b.get_updates())
    for u in b.updates:
        loop.create_task(b.parse_update(u))
    b.updates = list()
    print("Completed.")