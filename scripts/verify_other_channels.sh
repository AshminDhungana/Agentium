#!/bin/bash
# scripts/verify_other_channels.sh
echo "Verifying Other Channel Bridges implementation..."

# Check that all expected adapter files exist
ADAPTERS=(
    "backend/services/channels/slack.py"
    "backend/services/channels/telegram.py"
    "backend/services/channels/discord.py"
    "backend/services/channels/email.py"
    "backend/services/channels/sms_twilio.py"
    # Add others as they are implemented:
    # "backend/services/channels/signal.py"
    # "backend/services/channels/google_chat.py"
    # "backend/services/channels/teams.py"
    # "backend/services/channels/matrix.py"
    # "backend/services/channels/imessage.py"
    # "backend/services/channels/zalo.py"
)

MISSING=0
for adapter in "${ADAPTERS[@]}"; do
    if [ ! -f "$adapter" ]; then
        echo "❌ Missing adapter: $adapter"
        ((MISSING++))
    else
        echo "✅ Found adapter: $adapter"
    fi
done

if [ $MISSING -eq 0 ]; then
    echo "✅ All expected channel adapters are present"
else
    echo "❌ $MISSING adapter(s) missing"
    exit 1
fi

# Check that tests exist for each adapter
TEST_FILES=(
    "tests/backend/services/channels/test_slack_adapter.py"
    "tests/backend/services/channels/test_telegram_adapter.py"
    "tests/backend/services/channels/test_discord_adapter.py"
    "tests/backend/services/channels/test_email_adapter.py"
    "tests/backend/services/channels/test_sms_twilio_adapter.py"
    # Add others as they are implemented:
    # "tests/backend/services/channels/test_signal_adapter.py"
    # "tests/backend/services/channels/test_google_chat_adapter.py"
    # "tests/backend/services/channels/test_teams_adapter.py"
    # "tests/backend/services/channels/test_matrix_adapter.py"
    # "tests/backend/services/channels/test_imessage_adapter.py"
    # "tests/backend/services/channels/test_zalo_adapter.py"
)

MISSING_TESTS=0
for test_file in "${TEST_FILES[@]}"; do
    if [ ! -f "$test_file" ]; then
        echo "❌ Missing test file: $test_file"
        ((MISSING_TESTS++))
    else
        echo "✅ Found test file: $test_file"
    fi
done

if [ $MISSING_TESTS -eq 0 ]; then
    echo "✅ All expected test files are present"
else
    echo "❌ $MISSING_TESTS test file(s) missing"
    exit 1
fi

echo "✅ Other Channel Bridges verification structure is complete"