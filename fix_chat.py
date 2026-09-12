with open(r'E:\Ongoing Projects\Agentium\backend\api\routes\chat.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Replace all occurrences of current_user.get('user_id', '') with _get_user_id(current_user)
content = content.replace('current_user.get("user_id", "")', '_get_user_id(current_user)')

# Replace all occurrences of current_user["id"] with _get_user_id(current_user)
content = content.replace('current_user["id"]', '_get_user_id(current_user)')

# Replace str(current_user["id"]) with _get_user_id(current_user)
content = content.replace('str(current_user["id"])', '_get_user_id(current_user)')

# Replace str(current_user.get("id")) with _get_user_id(current_user)
content = content.replace('str(current_user.get("id"))', '_get_user_id(current_user)')

# Also fix the send_message function which uses current_user["id"]
content = content.replace('current_user["id"]', '_get_user_id(current_user)')

# Fix current_user.get("id") 
content = content.replace('current_user.get("id")', '_get_user_id(current_user)')

with open(r'E:\Ongoing Projects\Agentium\backend\api\routes\chat.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Replaced user_id references')