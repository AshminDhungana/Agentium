import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: overlay
    width: 320
    height: 320
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property real micLevel: 0.0
    property string voiceState: "idle"
    property color orbColor: "#3b82f6"

    opacity: 0

    Behavior on opacity {
        NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
    }

    onOpacityChanged: {
        visible = opacity > 0;
    }

    onVoiceStateChanged: {
        if (voiceState === "listening") orbColor = "#3b82f6";
        else if (voiceState === "thinking") orbColor = "#8b5cf6";
        else if (voiceState === "speaking") orbColor = "#10b981";
        else orbColor = "#3b82f6";
    }

    // Outer glow halo
    Rectangle {
        anchors.centerIn: parent
        width: 340
        height: 340
        radius: 170
        color: "transparent"
        border.color: {
            if (voiceState === "listening") return Qt.rgba(0.23, 0.51, 0.96, 0.3);
            if (voiceState === "speaking") return Qt.rgba(0.06, 0.72, 0.51, 0.3);
            if (voiceState === "thinking") return Qt.rgba(0.55, 0.24, 0.96, 0.3);
            return Qt.rgba(0.23, 0.51, 0.96, 0.15);
        }
        border.width: 2

        NumberAnimation on scale {
            running: overlay.voiceState !== "idle"
            from: 1.0; to: 1.03
            duration: 1500; easing.type: Easing.InOutSine
        }
    }

    // Canvas orb
    Canvas {
        id: orbCanvas
        anchors.fill: parent
        anchors.margins: 10

        property real time: 0

        function simplex2D(x, y) {
            return Math.sin(x * 3.0 + time) * 0.3 + Math.cos(y * 4.0 + time * 0.7) * 0.3;
        }

        onPaint: {
            var ctx = getContext("2d");
            var w = width, h = height;
            ctx.clearRect(0, 0, w, h);

            var cx = w / 2, cy = h / 2;
            var baseR = 90;
            var pointCount = 48;
            var amplitude = voiceState === "idle" ? 5 : 10 + micLevel * 25;

            time += 0.02;

            // Build blob path
            ctx.beginPath();
            for (var i = 0; i <= pointCount; i++) {
                var angle = (i / pointCount) * Math.PI * 2 - Math.PI / 2;
                var noise = 0;
                if (voiceState === "listening" || voiceState === "speaking") {
                    noise = simplex2D(cx + baseR * Math.cos(angle), cy + baseR * Math.sin(angle)) * amplitude;
                } else if (voiceState === "thinking") {
                    noise = Math.sin(time * 2 + i * 0.5) * 12;
                }
                var r = baseR + noise;
                var px = cx + Math.cos(angle) * r;
                var py = cy + Math.sin(angle) * r;
                if (i === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
            }
            ctx.closePath();

            // Fill with gradient
            var gradient = ctx.createRadialGradient(cx - 20, cy - 20, 10, cx, cy, baseR + 20);
            gradient.addColorStop(0, orbColor);
            gradient.addColorStop(0.5, orbColor + "cc");
            gradient.addColorStop(1, orbColor + "44");
            ctx.fillStyle = gradient;
            ctx.fill();

            // Inner glow highlight
            var innerGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 0.4);
            innerGlow.addColorStop(0, "rgba(255,255,255,0.15)");
            innerGlow.addColorStop(1, "rgba(255,255,255,0)");
            ctx.fillStyle = innerGlow;
            ctx.fill();
        }

        Connections {
            target: overlay
            function onMicLevelChanged() { orbCanvas.requestPaint(); }
            function onVoiceStateChanged() { orbCanvas.requestPaint(); }
        }
    }

    Timer {
        interval: 16
        running: opacity > 0
        repeat: true
        onTriggered: {
            orbCanvas.time += 0.02;
            orbCanvas.requestPaint();
        }
    }

    // Center dot
    Rectangle {
        width: 20
        height: 20
        radius: 10
        color: "#ffffff"
        opacity: 0.9
        anchors.centerIn: parent

        Rectangle {
            width: 8
            height: 8
            radius: 4
            color: "#ffffff"
            opacity: 0.4
            anchors.centerIn: parent
        }
    }

    // Orbital rings
    Repeater {
        model: 2
        Rectangle {
            x: parent.width / 2 - width / 2
            y: parent.height / 2 - height / 2
            width: 200 + index * 20
            height: 200 + index * 20
            radius: (width + height) / 4
            color: "transparent"
            border.color: "#143B82F6"
            border.width: 1
            rotation: orbCanvas.time * (index === 0 ? 15 : -10)
        }
    }
}
