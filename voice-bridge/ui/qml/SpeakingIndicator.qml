import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: indicator
    width: 120
    height: 36
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property bool active: false

    opacity: 0

    Behavior on opacity {
        NumberAnimation { duration: active ? 300 : 100; easing.type: Easing.OutCubic }
    }

    onOpacityChanged: {
        visible = opacity > 0;
    }

    Rectangle {
        id: glassBg
        anchors.fill: parent
        radius: 18
        color: "#D9161B27"
        border.color: "#4D3B82F6"
        border.width: 1

        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 0.8
            blurMax: 32
            saturation: 0.5
        }
    }

    Item {
        anchors.centerIn: parent
        width: childrenRect.width
        height: 16

        property real time: 0

        Timer {
            interval: 16
            running: true
            repeat: true
            onTriggered: {
                parent.time += 0.05;
            }
        }

        Row {
            spacing: 5
            Repeater {
                model: 3
                Rectangle {
                    y: parent.parent.height / 2 - height / 2
                    width: 3
                    radius: 1.5
                    color: "#3b82f6"

                    property real baseHeight: 8
                    height: indicator.active
                        ? baseHeight + Math.sin(parent.parent.time * 4 + index * 1.5) * 6 + 4
                        : baseHeight

                    Behavior on height {
                        NumberAnimation { duration: 80 }
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: 8
        width: 8
        height: 8
        radius: 4
        color: indicator.active ? "#3b82f6" : "transparent"

        Behavior on color {
            ColorAnimation { duration: 200 }
        }
    }
}
