import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: transcriptWindow
    width: 400
    height: 70
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property string transcriptText: ""
    property string transcriptRole: "user"
    property bool isVisible: false

    opacity: 0

    Behavior on opacity {
        NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
    }

    onOpacityChanged: {
        visible = opacity > 0;
    }

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: "#D9161B27"
        border.color: "#4D3B82F6"
        border.width: 1

        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 0.6
            blurMax: 24
            saturation: 0.5
        }
    }

    Text {
        id: label
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        color: transcriptRole === "user" ? "#3b82f6" : "#10b981"
        font.pixelSize: 13
        elide: Text.ElideRight
        maximumLineCount: 2
        text: (transcriptRole === "user" ? "You: " : "Agentium: ") + transcriptText
        visible: transcriptText.length > 0
    }

    onIsVisibleChanged: {
        opacity = isVisible ? 1.0 : 0.0;
    }
}
