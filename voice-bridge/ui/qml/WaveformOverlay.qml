import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: overlay
    width: 280
    height: 280
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property real micLevel: 0.0
    property string voiceState: "idle"

    opacity: 0

    Behavior on opacity {
        NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
    }

    onOpacityChanged: {
        visible = opacity > 0;
    }

    Rectangle {
        id: glassBg
        anchors.fill: parent
        radius: 140
        color: "#CC161B27"
        border.color: "#1A3B82F6"
        border.width: 1

        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 1.0
            blurMax: 64
            saturation: 0.5
        }
    }

    Canvas {
        id: waveformCanvas
        anchors.fill: parent
        anchors.margins: 10

        property real time: 0

        onPaint: {
            var ctx = getContext("2d");
            var w = width;
            var h = height;
            ctx.clearRect(0, 0, w, h);

            var cx = w / 2;
            var cy = h / 2;
            var radius = 90;
            var barCount = 48;
            var barWidth = 4;

            time += 0.02;

            for (var i = 0; i < barCount; i++) {
                var angle = (i / barCount) * Math.PI * 2 - Math.PI / 2;

                var level = 0.0;
                if (voiceState === "listening") {
                    level = micLevel * (0.6 + 0.4 * Math.sin(time * 3 + i * 0.4));
                } else if (voiceState === "thinking") {
                    var wavePos = ((time * 1.5 + i / barCount) % 1.0);
                    level = Math.sin(wavePos * Math.PI) * 0.5;
                }

                var barHeight = 6 + level * 30;
                var glowSize = level * 8;

                // Glow layer
                ctx.strokeStyle = "rgba(59, 130, 246, 0.15)";
                ctx.lineWidth = barWidth + glowSize;
                ctx.lineCap = "round";
                ctx.beginPath();
                var gx1 = cx + Math.cos(angle) * (radius - glowSize / 2);
                var gy1 = cy + Math.sin(angle) * (radius - glowSize / 2);
                var gx2 = cx + Math.cos(angle) * (radius + barHeight + glowSize / 2);
                var gy2 = cy + Math.sin(angle) * (radius + barHeight + glowSize / 2);
                ctx.moveTo(gx1, gy1);
                ctx.lineTo(gx2, gy2);
                ctx.stroke();

                // Main bar
                ctx.strokeStyle = "#3b82f6";
                ctx.lineWidth = barWidth;
                ctx.beginPath();
                var x1 = cx + Math.cos(angle) * radius;
                var y1 = cy + Math.sin(angle) * radius;
                var x2 = cx + Math.cos(angle) * (radius + barHeight);
                var y2 = cy + Math.sin(angle) * (radius + barHeight);
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.stroke();
            }
        }

        Connections {
            target: overlay
            function onMicLevelChanged() { waveformCanvas.requestPaint(); }
        }
    }

    Timer {
        interval: 16
        running: opacity > 0
        repeat: true
        onTriggered: {
            waveformCanvas.time += 0.02;
            waveformCanvas.requestPaint();
        }
    }

    // Core circle
    Rectangle {
        width: 16
        height: 16
        radius: 8
        color: "#3b82f6"
        anchors.centerIn: parent
        opacity: 0.9

        Rectangle {
            width: 8
            height: 8
            radius: 4
            color: "#ffffff"
            anchors.centerIn: parent
            opacity: 0.4
        }
    }

    // Orbital rings
    Repeater {
        model: 2
        Rectangle {
            x: parent.width / 2 - width / 2
            y: parent.height / 2 - height / 2
            width: 180 + index * 20
            height: 180 + index * 20
            radius: (width + height) / 4
            color: "transparent"
            border.color: "#143B82F6"
            border.width: 1
            rotation: waveformCanvas.time * (index === 0 ? 15 : -10)

            Behavior on rotation { NumberAnimation { duration: 100 } }
        }
    }
}
