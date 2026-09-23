const userInput = document.getElementById("userInput");
const sendButton = document.getElementById("sendButton");
const chatMessages = document.getElementById("chatMessages");
const newChatButton = document.getElementById("newChatButton");
const conversationList = document.getElementById("conversationList");


async function loadHistory() {
    const response = await fetch("/history");
    const data = await response.json();

    if (!response.ok) return;

    chatMessages.innerHTML = "";
    data.messages.forEach((message) => {
        const messageElement = document.createElement("div");
        messageElement.classList.add(
            "message",
            message.role === "user" ? "user-message" : "bot-message"
        );
        if (message.role === "user") {
            messageElement.textContent = message.content;
        } else {
            messageElement.innerHTML = marked.parse(message.content);
        }
        chatMessages.appendChild(messageElement);
    });
    chatMessages.scrollTop = chatMessages.scrollHeight;
}


async function loadConversations() {
    const response = await fetch("/conversations");
    const data = await response.json();
    if (!response.ok) return;

    conversationList.innerHTML = "";
    data.conversations.forEach((conversation) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "conversation-item";
        if (conversation.id === data.current_id) {
            button.classList.add("active");
        }
        button.textContent = conversation.title;
        button.addEventListener("click", async () => {
            await fetch("/select-chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({conversation_id: conversation.id})
            });
            await loadHistory();
            await loadConversations();
        });
        button.addEventListener("dblclick", async (event) => {
            event.preventDefault();
            const title = window.prompt("Nouveau nom de la conversation :", conversation.title);
            if (!title || !title.trim()) return;

            const renameResponse = await fetch("/rename-chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    conversation_id: conversation.id,
                    title: title.trim()
                })
            });
            if (renameResponse.ok) await loadConversations();
        });
        conversationList.appendChild(button);
    });
}


async function createNewChat() {
    const response = await fetch("/new-chat", {method: "POST"});
    if (!response.ok) return;
    chatMessages.innerHTML = "";
    await loadConversations();
    userInput.focus();
}


async function sendMessage() {

    const message = userInput.value.trim();

    if (!message) return;


    // User message
    const userMessage = document.createElement("div");

    userMessage.classList.add(
        "message",
        "user-message"
    );

    userMessage.textContent = message;

    chatMessages.appendChild(userMessage);


    // Clear input
    userInput.value = "";


    // Disable button while waiting
    sendButton.disabled = true;


    // Loading message
    const loadingMessage = document.createElement("div");

    loadingMessage.classList.add(
        "message",
        "bot-message"
    );

    loadingMessage.textContent = "...";

    chatMessages.appendChild(loadingMessage);

    chatMessages.scrollTop = chatMessages.scrollHeight;


    try {

        const response = await fetch("/chat", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message
            })

        });


        const data = await response.json();


        if (data.error) {

            loadingMessage.textContent =
                "Error: " + data.error;

        } else {

            // Convert Markdown to HTML
            loadingMessage.innerHTML =
                marked.parse(data.response);

        }

    } catch (error) {

        console.error(error);

        loadingMessage.textContent =
            "Connection error. Please try again.";

    } finally {

        // Enable button again
        sendButton.disabled = false;

        userInput.focus();

    }


    chatMessages.scrollTop =
        chatMessages.scrollHeight;
}


// Send button
sendButton.addEventListener(
    "click",
    sendMessage
);

newChatButton.addEventListener("click", createNewChat);


// Press Enter to send
userInput.addEventListener(
    "keydown",
    function (event) {

        if (event.key === "Enter") {

            sendMessage();

        }

    }
);

loadHistory();
loadConversations();