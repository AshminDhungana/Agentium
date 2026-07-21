import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: indicator
    width: 170
    height: 46
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property bool active: false
    property string stateLabel: "Speaking..."

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
        radius: 23
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
        height: 20

        property real time: 0

        Timer {
            interval: 16
            running: indicator.active
            repeat: true
            onTriggered: {
                parent.time += 0.05;
            }
        }

        Row {
            spacing: 6
            Repeater {
                model: 5
                Rectangle {
                    y: parent.parent.height / 2 - height / 2
                    width: 4
                    radius: 2
                    color: indicator.active ? "#3b82f6" : "#888888"

                    property real baseHeight: 10
                    height: indicator.active
                        ? baseHeight + Math.sin(parent.parent.time * 4 + index * 1.2) * 7 + 4
                        : baseHeight

                    Behavior on height {
                        NumberAnimation { duration: 80 }
                    }
                }
            }
        }
    }

    Text {
        anchors.left: parent.left
        anchors.leftMargin: 46
        anchors.verticalCenter: parent.verticalCenter
        color: "#cccccc"
        font.pixelSize: 11
        font.weight: Font.DemiBold
        text: indicator.stateLabel
        visible: indicator.active
    }

    Rectangle {
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        width: 10
        height: 10
        radius: 5
        color: indicator.active ? "#3b82f6" : "transparent"

        Behavior on color {
            ColorAnimation { duration: 200 }
        }
    }
}
