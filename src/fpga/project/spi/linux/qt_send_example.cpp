// Integrate in the existing ARM Qt application after V4L2 -> QImage conversion.
// Call on a worker thread. Keep any mmap-backed camera buffer valid until frame.copy().
#include <QImage>
#include <QProcess>
#include <QDir>
#include <QTemporaryFile>
#include <QString>
bool sendCameraImage(const QImage &capturedFrame, const QString &senderScript) {
    const QImage frame = capturedFrame.copy();
    QTemporaryFile file(QDir::tempPath() + "/labmate-spi-XXXXXX.jpg");
    if (!file.open()) return false;
    // Initial policy: resize and compress; no change to camera sensor/video pipeline.
    const QImage small = frame.scaled(320, 240, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    if (!small.save(&file, "JPEG", 60) || file.size() > 65536) return false;
    file.flush();
    QProcess sender;
    sender.start("python3", QStringList() << senderScript << file.fileName());
    if (!sender.waitForStarted(3000)) return false;
    if (!sender.waitForFinished(30000)) {
        sender.kill(); sender.waitForFinished(); return false;
    }
    return sender.exitStatus() == QProcess::NormalExit && sender.exitCode() == 0;
}
