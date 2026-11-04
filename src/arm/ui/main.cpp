#include <QApplication>
#include <QCloseEvent>
#include <QColor>
#include <QDialog>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QImageReader>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QLabel>
#include <QMessageBox>
#include <QPainter>
#include <QPainterPath>
#include <QSaveFile>
#include <QPlainTextEdit>
#include <QProcess>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QPixmap>
#include <QScrollArea>
#include <QScroller>
#include <QStandardPaths>
#include <QStringList>
#include <QTemporaryDir>
#include <QTableWidget>
#include <QTabWidget>
#include <QTimer>
#include <QUuid>
#include <QVBoxLayout>
#include <QWidget>
#include <initializer_list>
#include <cmath>

// The same ARM executable renders an immutable PNG without owning the LCD.
static bool renderSpectrum(const QString &input, const QString &output)
{
    QFile file(input);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 2000000) return false;
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) return false;
    const auto data = document.object();
    const auto bins = data.value(QStringLiteral("amplitudes_vpeak")).toArray();
    const int n = data.value(QStringLiteral("fft_size")).toInt();
    const double df = data.value(QStringLiteral("bin_spacing_hz")).toDouble();
    const QString backend = data.value(QStringLiteral("backend")).toString();
    const bool response = data.value(QStringLiteral("kind")).toString() == QStringLiteral("sweep_response");
    const auto frequencies = data.value(QStringLiteral("frequencies_hz")).toArray();
    if (response) {
        if (backend != QStringLiteral("scope_scpi") || bins.size() < 2 || bins.size() > 10000 || frequencies.size() != bins.size()) return false;
        double previous = 0;
        for (const auto &f : frequencies) {
            const double value = f.toDouble(-1);
            if (!f.isDouble() || !std::isfinite(value) || value <= 0 || value < previous) return false;
            previous = value;
        }
    } else if (n < 256 || n > 65536 || (n & (n-1)) || bins.size() != n/2+1 ||
        !std::isfinite(df) || df <= 0 || (backend != QStringLiteral("fpga") && backend != QStringLiteral("software_reference"))) return false;
    double highest = 0;
    for (const auto &bin : bins) {
        const double value = bin.toDouble(-1);
        if (!bin.isDouble() || !std::isfinite(value) || value < 0) return false;
        highest = qMax(highest, value);
    }
    QImage image(1000, 600, QImage::Format_RGB32);
    image.fill(QColor("#101b2b"));
    QPainter painter(&image);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setFont(QFont(QStringLiteral("DejaVu Sans"), 17));
    painter.setPen(QColor("#edf4ff"));
    painter.drawText(QRect(30, 16, 940, 35), Qt::AlignCenter,
                     response ? QStringLiteral("Continuous Sweep Response (approximate)") : backend == QStringLiteral("fpga") ? QStringLiteral("FPGA FFT Spectrum") : QStringLiteral("SOFTWARE REFERENCE - NOT FPGA"));
    painter.setFont(QFont(QStringLiteral("DejaVu Sans"), 11));
    painter.drawText(QRect(30, 57, 940, 28), Qt::AlignCenter,
                     response ? QStringLiteral("HOST4 / CH1 | %1 measured pairs | sequential readings (approximate)").arg(bins.size()) : QStringLiteral("SDS1202X / HOST4 / CH%1   N=%2   Fs=%3 Sa/s   df=%4 Hz   Hann / DC removed")
                     .arg(data.value(QStringLiteral("channel")).toInt()).arg(n)
                     .arg(data.value(QStringLiteral("sample_rate_hz")).toDouble(), 0, 'g', 6).arg(df, 0, 'g', 6));
    const QRectF plot(105, 115, 850, 355);
    const double top = highest > 0 ? highest*1.12 : 1;
    const double xmax = response ? frequencies.last().toDouble() : df*(bins.size()-1);
    for (int tick = 0; tick <= 5; ++tick) {
        const double x = plot.left()+plot.width()*tick/5.;
        const double y = plot.bottom()-plot.height()*tick/5.;
        painter.setPen(QPen(QColor("#2a3d55"), 1));
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()));
        painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y));
        painter.setPen(QColor("#c2d0e4"));
        painter.drawText(QRectF(x-66, plot.bottom()+10, 132, 28), Qt::AlignCenter,
                         QString::number(xmax*tick/5., 'g', 5));
        painter.drawText(QRectF(4, y-14, 89, 28), Qt::AlignRight | Qt::AlignVCenter,
                         QString::number(top*tick/5., 'g', 4));
    }
    painter.setPen(QPen(QColor("#94a9c2"), 1));
    painter.drawRect(plot);
    painter.save();
    painter.setClipRect(plot);
    QPainterPath curve;
    for (int k=0; k<bins.size(); ++k) {
        const QPointF point(plot.left()+plot.width()*(response ? frequencies[k].toDouble()/xmax : double(k)/(bins.size()-1.)), plot.bottom()-plot.height()*bins[k].toDouble()/top);
        if (!k) curve.moveTo(point); else curve.lineTo(point);
        if (response) { painter.setPen(QPen(QColor("#55d6e8"), 4)); painter.drawPoint(point); }
    }
    painter.setPen(QPen(QColor("#55d6e8"), 1.5));
    painter.drawPath(curve);
    painter.restore();
    painter.setPen(QColor("#edf4ff"));
    painter.drawText(QRect(100, 515, 850, 28), Qt::AlignCenter, QStringLiteral("Frequency (Hz)"));
    painter.drawText(QRect(10, 85, 220, 28), response ? QStringLiteral("Peak-to-peak (Vpp)") : QStringLiteral("Amplitude (Vpeak)"));
    painter.drawText(QRect(70, 552, 870, 28), Qt::AlignCenter,
                     (response ? QStringLiteral("Maximum measured: %1 Hz   %2 Vpp   |   %3") : QStringLiteral("Peak bin: %1 Hz   %2 Vpeak   |   %3"))
                     .arg(data.value(QStringLiteral("peak_frequency_hz")).toDouble(), 0, 'g', 7)
                     .arg(data.value(QStringLiteral("peak_amplitude_vpeak")).toDouble(), 0, 'g', 6)
                     .arg(data.value(QStringLiteral("captured_at")).toString()));
    painter.end();
    QSaveFile target(output);
    return target.open(QIODevice::WriteOnly) && image.save(&target, "PNG") && target.commit();
}

static void showSavedImage(QWidget *owner, const QString &path, const QString &title = QStringLiteral("示波器屏幕截图"))
{
    QDialog preview(owner);
    preview.setWindowTitle(title);
    preview.setFixedSize(800, 480);
    auto *layout = new QVBoxLayout(&preview);
    layout->setContentsMargins(8, 6, 8, 6);
    layout->setSpacing(4);
    auto *status = new QLabel(title + QStringLiteral(" · 放大后可滑动查看"));
    status->setWordWrap(true);
    layout->addWidget(status);
    auto *scroll = new QScrollArea;
    scroll->setAlignment(Qt::AlignCenter);
    scroll->setStyleSheet(QStringLiteral("QScrollArea {background:#000; border:0;}"));
    auto *picture = new QLabel;
    picture->setStyleSheet(QStringLiteral("background:#000;"));
    scroll->setWidget(picture);
    QScroller::grabGesture(scroll->viewport(), QScroller::LeftMouseButtonGesture);
    layout->addWidget(scroll, 1);
    auto *buttons = new QHBoxLayout;
    auto *fit = new QPushButton(QStringLiteral("适应屏幕"));
    auto *original = new QPushButton(QStringLiteral("原图"));
    auto *zoom = new QPushButton(QStringLiteral("两倍放大"));
    auto *close = new QPushButton(QStringLiteral("返回详情"));
    for (auto *button : {fit, original, zoom, close}) buttons->addWidget(button);
    layout->addLayout(buttons);
    QImageReader reader(path);
    reader.setAutoTransform(true);
    const QSize size = reader.size();
    QPixmap image;
    if (size.isValid() && size.width() <= 8192 && size.height() <= 8192 &&
            qint64(size.width()) * size.height() <= 32000000)
        image = QPixmap::fromImage(reader.read());
    const auto display = [picture, image](const QSize &target) {
        if (image.isNull()) return;
        const QPixmap scaled = image.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation);
        picture->setPixmap(scaled);
        picture->resize(scaled.size());
    };
    QObject::connect(fit, &QPushButton::clicked, &preview, [scroll, display]() { display(scroll->viewport()->size()); });
    QObject::connect(original, &QPushButton::clicked, &preview, [image, display]() { display(image.size()); });
    QObject::connect(zoom, &QPushButton::clicked, &preview, [image, display]() { display(image.size() * 2); });
    QObject::connect(close, &QPushButton::clicked, &preview, &QDialog::accept);
    if (image.isNull()) {
        status->setText(QFileInfo::exists(path) ? QStringLiteral("图片无法打开或尺寸不受支持，请查看记录详情中的路径。")
                                               : QStringLiteral("图片文件已不存在，请查看记录详情中的路径。"));
        for (auto *button : {fit, original, zoom}) button->setEnabled(false);
    } else {
        QTimer::singleShot(0, &preview, [scroll, display]() { display(scroll->viewport()->size()); });
    }
    preview.exec();
}

// Python owns operation state. This Qt application's stdout stays reserved for
// the future vendor desktop protocol; backend logs use a separate pipe.
class AssistantWindow : public QWidget
{
public:
    AssistantWindow()
    {
        m_real = !qgetenv("LABMATE_ASR_ROOT").isEmpty();
        setWindowTitle(m_real ? QStringLiteral("实验助手 · 真实语音") : QStringLiteral("实验助手 · Python 通信"));
        setFixedSize(800, 480);
        setStyleSheet(QStringLiteral(
            "QWidget {background:#101b2b; color:#e8eef7; font-size:16px;}"
            "QLabel#title {font-size:28px; font-weight:600;}"
            "QLabel#badge {color:#f2ca70; font-size:14px;}"
            "QGroupBox {border:1px solid #35445c; border-radius:10px;"
            " margin-top:12px; padding:12px;}"
            "QGroupBox::title {subcontrol-origin:margin; left:12px; padding:0 5px;}"
            "QPlainTextEdit {background:#17263b; border:0; font-size:15px;}"
            "QPushButton {background:#253a56; border:1px solid #48617f;"
            " border-radius:8px; padding:10px; min-height:30px;}"
            "QPushButton:pressed {background:#355478;}"
            "QPushButton:disabled {background:#18263a; color:#77879c; border-color:#293b52;}"
            "QPushButton#start {background:#1763c0; border-color:#3982dc;}"
            "QPushButton#reconnect, QPushButton#exit {font-size:14px; padding:6px; min-height:24px;}"
            "QTabWidget::pane {border:1px solid #35445c; border-radius:6px;}"
            "QTabBar::tab {background:#1b2c43; padding:9px 28px; margin-right:5px;}"
            "QTabBar::tab:selected {background:#1763c0;}"
            "QTableWidget {background:#17263b; border:0; gridline-color:#35445c; font-size:15px;}"
            "QTableWidget::item:selected {background:#285788; color:#ffffff;}"
            "QHeaderView::section {background:#253a56; padding:7px; border:0; font-size:14px;}"
            "QScrollBar:vertical {width:22px;}"));

        auto *layout = new QVBoxLayout(this);
        layout->setContentsMargins(16, 10, 16, 10);
        layout->setSpacing(6);
        auto *header = new QHBoxLayout;
        auto *title = new QLabel(QStringLiteral("实验助手"));
        title->setObjectName(QStringLiteral("title"));
        m_badge = new QLabel(QStringLiteral("正在连接 Python 后台"));
        m_badge->setObjectName(QStringLiteral("badge"));
        m_reconnect = new QPushButton(QStringLiteral("重新连接"));
        m_reconnect->setObjectName(QStringLiteral("reconnect"));
        m_exit = new QPushButton(QStringLiteral("关闭助手"));
        m_exit->setObjectName(QStringLiteral("exit"));
        header->addWidget(title);
        header->addStretch();
        header->addWidget(m_badge);
        header->addWidget(m_reconnect);
        header->addWidget(m_exit);
        layout->addLayout(header);

        m_status = new QLabel;
        m_status->setWordWrap(true);
        layout->addWidget(m_status);
        m_tabs = new QTabWidget;
        layout->addWidget(m_tabs, 1);
        auto *recognitionPage = new QWidget;
        auto *recognitionLayout = new QVBoxLayout(recognitionPage);
        recognitionLayout->setContentsMargins(10, 4, 10, 8);
        recognitionLayout->setSpacing(5);
        m_tabs->addTab(recognitionPage, QStringLiteral("语音识别"));
        auto *resultBox = new QGroupBox(QStringLiteral("识别与理解结果"));
        auto *resultLayout = new QVBoxLayout(resultBox);
        m_result = new QLabel(QStringLiteral("连接成功后，点击“开始识别”。"));
        m_result->setWordWrap(true);
        m_command = new QLabel(m_real ? QStringLiteral("先等待模型与麦克风就绪，再点击开始说话。")
                                      : QStringLiteral("本轮先验证 Python 通信，识别结果使用模拟数据。"));
        m_command->setWordWrap(true);
        resultLayout->addWidget(m_result);
        resultLayout->addWidget(m_command);
        m_viewSpectrum = new QPushButton(QStringLiteral("查看本次频谱图"));
        m_viewSpectrum->setEnabled(false);
        resultLayout->addWidget(m_viewSpectrum);
        connect(m_viewSpectrum, &QPushButton::clicked, this, [this]() {
            if (!m_spectrumPath.isEmpty()) showSavedImage(this, m_spectrumPath, QStringLiteral("FFT 频谱图"));
        });
        recognitionLayout->addWidget(resultBox);
        auto *logBox = new QGroupBox(QStringLiteral("过程提示"));
        auto *logLayout = new QVBoxLayout(logBox);
        m_log = new QPlainTextEdit;
        m_log->setReadOnly(true);
        m_log->setMaximumBlockCount(80);
        logLayout->addWidget(m_log);
        recognitionLayout->addWidget(logBox, 1);

        auto *buttons = new QGridLayout;
        m_start = new QPushButton(QStringLiteral("开始识别"));
        m_start->setObjectName(QStringLiteral("start"));
        m_calibrate = new QPushButton(QStringLiteral("语音检测"));
        m_confirm = new QPushButton(m_real ? QStringLiteral("确认保存") : QStringLiteral("确认演示"));
        m_cancel = new QPushButton(QStringLiteral("取消"));
        buttons->addWidget(m_start, 0, 0);
        buttons->addWidget(m_calibrate, 0, 1);
        buttons->addWidget(m_confirm, 0, 2);
        buttons->addWidget(m_cancel, 0, 3);
        for (int column = 0; column < 4; ++column) buttons->setColumnStretch(column, 1);
        recognitionLayout->addLayout(buttons);

        auto *historyPage = new QWidget;
        auto *historyLayout = new QVBoxLayout(historyPage);
        historyLayout->setContentsMargins(8, 6, 8, 6);
        historyLayout->setSpacing(5);
        auto *historyHeader = new QHBoxLayout;
        auto *historyHint = new QLabel(QStringLiteral("点选记录查看详情 · 时间按北京时间显示"));
        historyHint->setStyleSheet(QStringLiteral("font-size:14px; color:#b9c9df;"));
        m_refresh = new QPushButton(QStringLiteral("刷新记录"));
        m_refresh->setStyleSheet(QStringLiteral("padding:5px 14px; min-height:26px;"));
        historyHeader->addWidget(historyHint, 1);
        historyHeader->addWidget(m_refresh);
        m_clearAll = new QPushButton(QStringLiteral("清除全部记录"));
        m_clearAll->setStyleSheet(QStringLiteral("padding:5px 14px; min-height:26px; color:#ffb8b8;"));
        historyHeader->addWidget(m_clearAll);
        historyLayout->addLayout(historyHeader);
        m_history = new QTableWidget(0, 4);
        m_history->setHorizontalHeaderLabels(QStringList() << QStringLiteral("数据内容") << QStringLiteral("记录时间")
                                             << QStringLiteral("来源") << QStringLiteral("状态"));
        m_history->setEditTriggers(QAbstractItemView::NoEditTriggers);
        m_history->setSelectionBehavior(QAbstractItemView::SelectRows);
        m_history->setSelectionMode(QAbstractItemView::SingleSelection);
        m_history->setWordWrap(true);
        m_history->verticalHeader()->hide();
        m_history->verticalHeader()->setDefaultSectionSize(46);
        m_history->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
        for (int column = 1; column < 4; ++column)
            m_history->horizontalHeader()->setSectionResizeMode(column, QHeaderView::Fixed);
        m_history->setColumnWidth(1, 176);
        m_history->setColumnWidth(2, 92);
        m_history->setColumnWidth(3, 62);
        historyLayout->addWidget(m_history, 1);
        m_historyStatus = new QLabel(QStringLiteral("正在连接后台，准备读取历史记录……"));
        m_historyStatus->setWordWrap(true);
        m_historyStatus->setStyleSheet(QStringLiteral("font-size:13px; color:#f2ca70;"));
        historyLayout->addWidget(m_historyStatus);
        auto *pages = new QHBoxLayout;
        m_previous = new QPushButton(QStringLiteral("上一页"));
        m_next = new QPushButton(QStringLiteral("下一页"));
        m_pageLabel = new QLabel(QStringLiteral("第 1 / 1 页 · 共 0 条"));
        m_pageLabel->setAlignment(Qt::AlignCenter);
        for (auto *button : {m_previous, m_next})
            button->setStyleSheet(QStringLiteral("padding:6px 20px; min-height:28px;"));
        pages->addWidget(m_previous);
        pages->addWidget(m_pageLabel, 1);
        pages->addWidget(m_next);
        historyLayout->addLayout(pages);
        m_tabs->addTab(historyPage, QStringLiteral("历史记录"));

        m_process = new QProcess(this);
        m_process->setProcessChannelMode(QProcess::SeparateChannels);
        m_startupTimer = new QTimer(this);
        m_requestTimer = new QTimer(this);
        m_operationTimer = new QTimer(this);
        m_historyTimer = new QTimer(this);
        m_historyEditTimer = new QTimer(this);
        for (auto *timer : {m_startupTimer, m_requestTimer, m_operationTimer, m_historyTimer, m_historyEditTimer}) timer->setSingleShot(true);
        connect(m_start, &QPushButton::clicked, this, [this]() { startRecognition(); });
        connect(m_calibrate, &QPushButton::clicked, this, [this]() {
            if (m_phase != Idle || !m_pendingId.isEmpty()) return;
            m_operationId = newId();
            m_result->setText(QStringLiteral("语音检测：按提示分三次说“记录数据”。"));
            m_command->setText(QStringLiteral("仅检测解码和声道，不执行仪器读取或保存；可点“取消”中止。"));
            sendRequest(QStringLiteral("calibrate"), m_operationId);
        });
        connect(m_confirm, &QPushButton::clicked, this, [this]() {
            if (m_phase == Pending && m_pendingId.isEmpty()) sendRequest(QStringLiteral("confirm"));
        });
        connect(m_cancel, &QPushButton::clicked, this, [this]() {
            if ((m_phase == Running || m_phase == Pending) && m_pendingId.isEmpty())
                sendRequest(QStringLiteral("cancel"));
        });
        connect(m_exit, &QPushButton::clicked, this, &QWidget::close);
        connect(m_refresh, &QPushButton::clicked, this, [this]() { requestHistory(0); });
        connect(m_clearAll, &QPushButton::clicked, this, [this]() { requestHistoryClear(); });
        connect(m_previous, &QPushButton::clicked, this, [this]() { requestHistory(m_historyPage - 1); });
        connect(m_next, &QPushButton::clicked, this, [this]() { requestHistory(m_historyPage + 1); });
        connect(m_history, &QTableWidget::cellClicked, this, [this](int row, int) { showRecord(row); });
        connect(m_tabs, &QTabWidget::currentChanged, this, [this](int index) {
            if (index == 1 && m_historyRequestId.isEmpty()) requestHistory(m_historyPage);
        });
        connect(m_reconnect, &QPushButton::clicked, this, [this]() { startBackend(); });
        connect(m_process, &QProcess::started, this, [this]() { requestHistory(0); });
        connect(m_process, &QProcess::readyReadStandardOutput, this, [this]() { readBackend(); });
        connect(m_process, &QProcess::readyReadStandardError, this, [this]() {
            const QByteArray data = m_process->readAllStandardError();
            if (!m_closing) log(QStringLiteral("[后台日志] ") + QString::fromUtf8(data).right(2000));
        });
        connect(m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
            if (m_closing) {
                if (m_process->state() == QProcess::NotRunning) finishClosing();
                return;
            }
            if (error == QProcess::FailedToStart)
                failBackend(QStringLiteral("Python 启动失败：") + m_process->errorString());
            else if (error != QProcess::Crashed)
                failBackend(QStringLiteral("Python 通信错误：") + m_process->errorString());
        });
        connect(m_process, static_cast<void (QProcess::*)(int, QProcess::ExitStatus)>(&QProcess::finished),
                this, [this](int code, QProcess::ExitStatus) {
            if (m_closing) { finishClosing(); return; }
            if (m_failure.isEmpty()) m_failure = QStringLiteral("Python 后台已退出（代码 %1），请重新连接。").arg(code);
            markOffline(m_failure);
        });
        connect(m_startupTimer, &QTimer::timeout, this, [this]() {
            failBackend(QStringLiteral("Python 后台启动超时，请重新连接。"));
        });
        connect(m_requestTimer, &QTimer::timeout, this, [this]() {
            failBackend(QStringLiteral("Python 后台没有回应本次指令，请重新连接。"));
        });
        connect(m_operationTimer, &QTimer::timeout, this, [this]() {
            if (m_phase == Saving) {
                m_status->setText(QStringLiteral("状态：仍在等待保存完成，请勿重复操作；可稍后查看历史记录核对。"));
                return;
            }
            failBackend(QStringLiteral("等待识别结果超时，请重新连接。"));
        });
        connect(m_historyTimer, &QTimer::timeout, this, [this]() {
            m_historyRequestId.clear();
            m_historyRefreshPending = false;
            m_historyStatus->setText(QStringLiteral("历史读取超时，已保留上次列表；请点击刷新重试。"));
            updateButtons();
        });
        connect(m_historyEditTimer, &QTimer::timeout, this, [this]() {
            m_historyEditId.clear();
            log(QStringLiteral("清除响应超时，正在刷新确认结果。"));
            updateButtons();
            requestHistory(0);
        });
        log(m_real ? QStringLiteral("真实麦克风与 Vosk 模式；口述具体电压/电流后确认保存，历史页可查看已保存数据。")
                   : QStringLiteral("当前使用模拟识别；设置真实语音启动环境后再接入板载麦克风。"));
        setPhase(Connecting, QStringLiteral("正在启动 Python 后台……"));
        QTimer::singleShot(0, this, [this]() { startBackend(); });
    }

protected:
    void closeEvent(QCloseEvent *event) override
    {
        if (m_allowClose || m_process->state() == QProcess::NotRunning) { event->accept(); return; }
        event->ignore();
        if (m_closing) return;
        m_closing = true;
        stopTimers();
        updateButtons();
        m_status->setText(QStringLiteral("状态：正在关闭 Python 后台……"));
        QJsonObject request;
        request.insert(QStringLiteral("protocol"), 1);
        request.insert(QStringLiteral("id"), newId());
        request.insert(QStringLiteral("action"), QStringLiteral("quit"));
        m_process->write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n');
        m_process->closeWriteChannel();
        QTimer::singleShot(m_real ? 12000 : 1500, this, [this]() {
            if (m_process->state() != QProcess::NotRunning) m_process->terminate();
        });
        QTimer::singleShot(m_real ? 30000 : 3000, this, [this]() {
            if (m_process->state() != QProcess::NotRunning) m_process->kill();
        });
    }

private:
    enum Phase { Offline, Connecting, Idle, Running, Pending, Saving };
    Phase m_phase = Connecting;
    QLabel *m_status = nullptr;
    QLabel *m_badge = nullptr;
    QLabel *m_result = nullptr;
    QLabel *m_command = nullptr;
    QPushButton *m_viewSpectrum = nullptr;
    QString m_spectrumPath;
    QPlainTextEdit *m_log = nullptr;
    QPushButton *m_start = nullptr;
    QPushButton *m_calibrate = nullptr;
    QPushButton *m_confirm = nullptr;
    QPushButton *m_clearAll = nullptr;
    QTimer *m_historyEditTimer = nullptr;
    QString m_historyEditId;
    QString m_historyRevision;
    int m_historyTotal = 0;
    QPushButton *m_cancel = nullptr;
    QPushButton *m_reconnect = nullptr;
    QPushButton *m_exit = nullptr;
    QTabWidget *m_tabs = nullptr;
    QTableWidget *m_history = nullptr;
    QPushButton *m_refresh = nullptr;
    QPushButton *m_previous = nullptr;
    QPushButton *m_next = nullptr;
    QLabel *m_historyStatus = nullptr;
    QLabel *m_pageLabel = nullptr;
    QProcess *m_process = nullptr;
    QTimer *m_startupTimer = nullptr;
    QTimer *m_requestTimer = nullptr;
    QTimer *m_operationTimer = nullptr;
    QTimer *m_historyTimer = nullptr;
    QTemporaryDir m_backendDir;
    QByteArray m_stdout;
    QString m_operationId, m_pendingId, m_pendingAction, m_failure;
    QString m_historyRequestId, m_saveRequestId;
    QJsonArray m_historyRows;
    int m_historyPage = 0;
    int m_historyPages = 1;
    bool m_historyRefreshPending = false;
    bool m_closing = false;
    bool m_allowClose = false;
    bool m_real = false;

    static QString newId() { return QUuid::createUuid().toString(); }
    void log(const QString &message) { m_log->appendPlainText(message); }
    void stopTimers() { m_startupTimer->stop(); m_requestTimer->stop(); m_operationTimer->stop(); m_historyTimer->stop(); m_historyEditTimer->stop(); }
    void clearPending() { m_pendingId.clear(); m_pendingAction.clear(); m_requestTimer->stop(); }
    void updateButtons()
    {
        const bool available = !m_closing && m_pendingId.isEmpty() && m_historyEditId.isEmpty();
        m_start->setEnabled(available && m_phase == Idle);
        m_calibrate->setEnabled(available && m_phase == Idle && m_real);
        m_confirm->setEnabled(available && m_phase == Pending);
        m_cancel->setEnabled(available && (m_phase == Running || m_phase == Pending));
        m_reconnect->setEnabled(!m_closing && m_phase == Offline && m_process->state() == QProcess::NotRunning);
        const bool historyAvailable = !m_closing && m_phase != Offline &&
                m_process->state() == QProcess::Running && m_historyRequestId.isEmpty() && m_historyEditId.isEmpty();
        m_refresh->setEnabled(historyAvailable);
        m_clearAll->setEnabled(historyAvailable && m_phase == Idle && m_historyTotal > 0);
        m_history->setEnabled(!m_closing && m_historyEditId.isEmpty());
        m_previous->setEnabled(historyAvailable && m_historyPage > 0);
        m_next->setEnabled(historyAvailable && m_historyPage + 1 < m_historyPages);
        m_exit->setEnabled(!m_closing);
    }
    void setPhase(Phase phase, const QString &message)
    {
        m_phase = phase;
        m_status->setText(QStringLiteral("状态：") + message);
        updateButtons();
    }
    void markOffline(const QString &message)
    {
        stopTimers(); clearPending(); m_operationId.clear(); m_stdout.clear();
        m_saveRequestId.clear(); m_historyRequestId.clear(); m_historyRefreshPending = false;
        m_historyEditId.clear();
        m_historyStatus->setText(QStringLiteral("后台未连接，列表保留上次读取结果。"));
        m_badge->setText(QStringLiteral("后台未连接"));
        m_result->setText(QStringLiteral("连接中断，本轮结果已失效。")); m_command->clear();
        setPhase(Offline, message);
        log(message);
    }
    void failBackend(const QString &message)
    {
        if (m_closing) return;
        m_failure = message;
        markOffline(message);
        if (m_process->state() != QProcess::NotRunning) {
            const qint64 failedPid = m_process->processId();
            m_process->terminate();
            QTimer::singleShot(30000, this, [this, failedPid]() {
                if (m_process->state() != QProcess::NotRunning && m_process->processId() == failedPid)
                    m_process->kill();
            });
        }
    }
    void finishClosing()
    {
        m_allowClose = true;
        QTimer::singleShot(0, this, [this]() { close(); });
    }
    void startBackend()
    {
        if (m_closing || m_process->state() != QProcess::NotRunning) return;
        stopTimers(); clearPending(); m_operationId.clear(); m_stdout.clear(); m_failure.clear();
        m_saveRequestId.clear(); m_historyRequestId.clear(); m_historyRefreshPending = false;
        m_historyEditId.clear();
        m_badge->setText(QStringLiteral("正在连接 Python 后台"));
        setPhase(Connecting, QStringLiteral("正在启动 Python 后台……"));
        // External backend supports future Python-only updates; embedded files
        // still allow standalone desktop preview with one executable.
        QString scriptPath = QString::fromLocal8Bit(qgetenv("LABMATE_BACKEND"));
        if (!scriptPath.isEmpty()) {
            if (!QFileInfo(scriptPath).isAbsolute() || !QFileInfo::exists(scriptPath)) {
                failBackend(QStringLiteral("LABMATE_BACKEND 必须指向存在的绝对路径。")); return;
            }
        } else {
            if (!m_backendDir.isValid()) {
                failBackend(QStringLiteral("无法准备 Python 后台临时目录。")); return;
            }
            if (!QDir(m_backendDir.path()).mkpath(QStringLiteral("asr_runtime"))) {
                failBackend(QStringLiteral("无法准备记录格式模块目录。")); return;
            }
            for (const QString &name : {QStringLiteral("backend.py"), QStringLiteral("asr_adapter.py"),
                                       QStringLiteral("record_store.py"), QStringLiteral("instrument_adapter.py"),
                                       QStringLiteral("command_executor.py"), QStringLiteral("audio_frontend.py"),
                                       QStringLiteral("fft_control.py"), QStringLiteral("fft_protocol.py"), QStringLiteral("scope_waveform.py"), QStringLiteral("sweep_response.py"),
                                       QStringLiteral("generator_control.py"), QStringLiteral("generator_runner.py"),
                                       QStringLiteral("asr_runtime/generator_commands.py"), QStringLiteral("asr_runtime/main.py")}) {
                QFile source(QStringLiteral(":/backend/") + name);
                QFile destination(m_backendDir.filePath(name));
                if (!source.open(QIODevice::ReadOnly) || !destination.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                    failBackend(QStringLiteral("无法准备 Python 后台文件。")); return;
                }
                const QByteArray script = source.readAll();
                if (destination.write(script) != script.size() || !destination.flush()) {
                    failBackend(QStringLiteral("写入 Python 后台文件失败。")); return;
                }
            }
            scriptPath = m_backendDir.filePath(QStringLiteral("backend.py"));
        }
        QString python = QString::fromLocal8Bit(qgetenv("LABMATE_PYTHON"));
        if (python.isEmpty()) python = QStandardPaths::findExecutable(QStringLiteral("python3"));
        if (python.isEmpty()) { failBackend(QStringLiteral("找不到 python3，请在 Ubuntu 中安装 Python 3。")); return; }
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        environment.insert(QStringLiteral("PYTHONIOENCODING"), QStringLiteral("utf-8"));
        m_process->setProcessEnvironment(environment);
        m_process->setWorkingDirectory(m_backendDir.path());
        m_process->setProgram(python);
        m_process->setArguments(QStringList() << QStringLiteral("-u") << scriptPath);
        m_process->start();
        m_startupTimer->start(m_real ? 180000 : 10000);
    }
    void startRecognition()
    {
        if (m_phase != Idle || !m_pendingId.isEmpty()) return;
        m_operationId = newId();
        m_result->setText(QStringLiteral("正在等待 Python 后台处理……"));
        m_command->setText(m_real ? QStringLiteral("等待“现在请说话”提示后，说一句完整实验指令。")
                                 : QStringLiteral("当前使用模拟识别；计时不代表真实语音识别耗时。"));
        sendRequest(QStringLiteral("start"), m_operationId);
    }
    void requestHistory(int page)
    {
        if (m_closing || m_phase == Offline || m_process->state() != QProcess::Running || !m_historyEditId.isEmpty()) return;
        if (!m_historyRequestId.isEmpty()) { m_historyRefreshPending = true; return; }
        m_historyRequestId = newId();
        QJsonObject request;
        request.insert(QStringLiteral("protocol"), 1);
        request.insert(QStringLiteral("id"), m_historyRequestId);
        request.insert(QStringLiteral("action"), QStringLiteral("history"));
        request.insert(QStringLiteral("page"), qMax(0, page));
        request.insert(QStringLiteral("size"), 4);
        m_historyStatus->setText(QStringLiteral("正在读取已保存的记录……"));
        m_historyTimer->start(20000);
        updateButtons();
        if (m_process->write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n') < 0) {
            m_historyTimer->stop(); m_historyRequestId.clear();
            m_historyStatus->setText(QStringLiteral("历史请求发送失败，请刷新重试。"));
            updateButtons();
        }
    }
    void requestHistoryClear(const QString &recordId = QString())
    {
        if (m_closing || m_phase != Idle || !m_historyEditId.isEmpty() ||
                !m_historyRequestId.isEmpty() || !m_pendingId.isEmpty() || m_process->state() != QProcess::Running) return;
        QMessageBox box(QMessageBox::Warning, QStringLiteral("确认清除"),
            recordId.isEmpty() ? QStringLiteral("清除全部 %1 条历史记录？清除后将不再显示。").arg(m_historyTotal)
                               : QStringLiteral("清除这条历史记录？清除后将不再显示。"),
            QMessageBox::NoButton, this);
        auto *accept = box.addButton(QStringLiteral("确认清除"), QMessageBox::DestructiveRole);
        auto *cancel = box.addButton(QStringLiteral("取消"), QMessageBox::RejectRole);
        box.setDefaultButton(cancel);
        box.exec();
        if (box.clickedButton() != accept) return;
        if (m_closing || m_phase != Idle || m_process->state() != QProcess::Running) return;
        m_historyEditId = newId();
        QJsonObject request;
        request.insert(QStringLiteral("protocol"), 1);
        request.insert(QStringLiteral("id"), m_historyEditId);
        request.insert(QStringLiteral("action"), recordId.isEmpty() ? QStringLiteral("clear_history") : QStringLiteral("delete_record"));
        if (recordId.isEmpty()) request.insert(QStringLiteral("revision"), m_historyRevision);
        else request.insert(QStringLiteral("record_id"), recordId);
        m_historyStatus->setText(QStringLiteral("正在清除历史记录……"));
        m_historyEditTimer->start(20000);
        updateButtons();
        if (m_process->write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n') < 0) {
            m_historyEditTimer->stop(); m_historyEditId.clear();
            m_historyStatus->setText(QStringLiteral("清除请求发送失败，请刷新后重试。"));
            updateButtons();
        }
    }
    void showRecord(int row)
    {
        if (row < 0 || row >= m_historyRows.size()) return;
        const QJsonObject record = m_historyRows.at(row).toObject();
        QDialog dialog(this);
        dialog.setWindowTitle(QStringLiteral("实验记录详情"));
        dialog.setFixedSize(740, 420);
        auto *content = new QVBoxLayout(&dialog);
        auto *heading = new QLabel(record.value(QStringLiteral("content")).toString());
        heading->setWordWrap(true);
        content->addWidget(heading);
        auto *detail = new QPlainTextEdit;
        detail->setReadOnly(true);
        detail->setPlainText(record.value(QStringLiteral("detail")).toString());
        content->addWidget(detail, 1);
        const QString imagePath = record.value(QStringLiteral("image_path")).toString();
        if (!imagePath.isEmpty()) {
            const bool spectrum = record.value(QStringLiteral("image_kind")).toString() == QStringLiteral("spectrum");
            const bool response = record.value(QStringLiteral("image_kind")).toString() == QStringLiteral("sweep_response");
            const QString imageTitle = response ? QStringLiteral("扫频响应曲线") : spectrum ? QStringLiteral("FFT 频谱图") : QStringLiteral("示波器屏幕截图");
            auto *viewImage = new QPushButton(response ? QStringLiteral("查看响应曲线") : spectrum ? QStringLiteral("查看频谱图") : QStringLiteral("查看示波器截图"));
            viewImage->setObjectName(QStringLiteral("viewSavedImage"));
            content->addWidget(viewImage);
            connect(viewImage, &QPushButton::clicked, &dialog, [&dialog, imagePath, imageTitle]() {
                showSavedImage(&dialog, imagePath, imageTitle);
            });
        }
        auto *close = new QPushButton(QStringLiteral("返回历史列表"));
        auto *remove = new QPushButton(QStringLiteral("清除这条记录"));
        remove->setStyleSheet(QStringLiteral("color:#ffb8b8;"));
        remove->setEnabled(m_phase == Idle && m_pendingId.isEmpty() && m_historyEditId.isEmpty() && m_historyRequestId.isEmpty());
        content->addWidget(remove);
        connect(remove, &QPushButton::clicked, &dialog, [this, &dialog, record]() {
            requestHistoryClear(record.value(QStringLiteral("record_id")).toString());
            if (!m_historyEditId.isEmpty()) dialog.accept();
        });
        content->addWidget(close);
        connect(close, &QPushButton::clicked, &dialog, &QDialog::accept);
        dialog.exec();
    }
    void showHistory(const QJsonObject &message)
    {
        m_historyRows = message.value(QStringLiteral("rows")).toArray();
        m_historyPage = message.value(QStringLiteral("page")).toInt();
        m_historyPages = qMax(1, message.value(QStringLiteral("total_pages")).toInt());
        m_historyTotal = message.value(QStringLiteral("total")).toInt();
        m_historyRevision = message.value(QStringLiteral("revision")).toString();
        m_history->setRowCount(m_historyRows.size());
        for (int row = 0; row < m_historyRows.size(); ++row) {
            const QJsonObject record = m_historyRows.at(row).toObject();
            const QStringList fields = QStringList() << QStringLiteral("content") << QStringLiteral("time_text")
                                                     << QStringLiteral("source") << QStringLiteral("status");
            for (int column = 0; column < fields.size(); ++column) {
                auto *item = new QTableWidgetItem(record.value(fields.at(column)).toString());
                item->setToolTip(record.value(QStringLiteral("detail")).toString());
                if (record.value(QStringLiteral("simulated")).toBool()) item->setForeground(QColor(QStringLiteral("#f2ca70")));
                m_history->setItem(row, column, item);
            }
        }
        m_pageLabel->setText(QStringLiteral("第 %1 / %2 页 · 共 %3 条").arg(m_historyPage + 1).arg(m_historyPages)
                             .arg(message.value(QStringLiteral("total")).toInt()));
        QStringList warnings;
        for (const QJsonValue &warning : message.value(QStringLiteral("warnings")).toArray()) warnings << warning.toString();
        m_historyStatus->setText(!warnings.isEmpty() ? warnings.join(QStringLiteral("；")) :
                                m_historyRows.isEmpty() ? QStringLiteral("尚无已保存的实验记录。") :
                                QStringLiteral("已按记录编号去重，最新保存的记录在前。"));
    }
    void sendRequest(const QString &action, const QString &id = QString())
    {
        if (m_closing || m_process->state() != QProcess::Running || !m_pendingId.isEmpty()) return;
        m_pendingId = id.isEmpty() ? newId() : id;
        m_pendingAction = action;
        QJsonObject request;
        request.insert(QStringLiteral("protocol"), 1);
        request.insert(QStringLiteral("id"), m_pendingId);
        request.insert(QStringLiteral("action"), action);
        if (action != QStringLiteral("start")) request.insert(QStringLiteral("target"), m_operationId);
        log(QStringLiteral("[Qt → Python] ") + action + QStringLiteral(" · ") + m_operationId.mid(1, 8));
        updateButtons();
        m_requestTimer->start(5000);
        if (m_process->write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n') < 0)
            failBackend(QStringLiteral("发送后台指令失败，请重新连接。"));
    }
    void readBackend()
    {
        const QByteArray incoming = m_process->readAllStandardOutput();
        if (m_closing || m_phase == Offline) return;
        m_stdout += incoming;
        int newline;
        while ((newline = m_stdout.indexOf('\n')) >= 0) {
            const QByteArray line = m_stdout.left(newline);
            m_stdout.remove(0, newline + 1);
            if (line.size() > 65536) { failBackend(QStringLiteral("后台消息过长。")); return; }
            if (line.trimmed().isEmpty()) continue;
            QJsonParseError error;
            const QJsonDocument document = QJsonDocument::fromJson(line, &error);
            if (error.error != QJsonParseError::NoError || !document.isObject()) {
                failBackend(QStringLiteral("后台通信格式错误，请重新连接。")); return;
            }
            handleEvent(document.object());
            if (m_phase == Offline) return;
        }
        if (m_stdout.size() > 65536) failBackend(QStringLiteral("后台消息缺少结束标记。"));
    }
    void handleEvent(const QJsonObject &message)
    {
        if (message.value(QStringLiteral("protocol")).toInt() != 1 ||
                message.value(QStringLiteral("mode")).toString() != (m_real ? QStringLiteral("asr") : QStringLiteral("demo"))) {
            failBackend(QStringLiteral("后台协议或运行模式不匹配。")); return;
        }
        const QString event = message.value(QStringLiteral("event")).toString();
        const QString id = message.value(QStringLiteral("request_id")).toString();
        const QString operation = message.value(QStringLiteral("operation_id")).toString();
        const QString state = message.value(QStringLiteral("state")).toString();
        const QString text = message.value(QStringLiteral("message")).toString();
        if (event == QStringLiteral("fatal")) { failBackend(text); return; }
        if (!m_historyEditId.isEmpty() && id == m_historyEditId &&
                (event == QStringLiteral("history_cleared") || event == QStringLiteral("error"))) {
            m_historyEditTimer->stop(); m_historyEditId.clear();
            log(QStringLiteral("[历史记录] ") + text);
            m_historyStatus->setText(text);
            updateButtons();
            requestHistory(0);
            return;
        }
        // History replies use their own request id/timer and never change the
        // recognition operation, including during initialization and saving.
        if (event == QStringLiteral("history") ||
                (event == QStringLiteral("error") && !m_historyRequestId.isEmpty() && id == m_historyRequestId)) {
            if (id != m_historyRequestId || m_historyRequestId.isEmpty()) return;
            m_historyTimer->stop(); m_historyRequestId.clear();
            if (event == QStringLiteral("history")) showHistory(message);
            else m_historyStatus->setText(text);
            updateButtons();
            if (m_historyRefreshPending) { m_historyRefreshPending = false; requestHistory(0); }
            return;
        }
        if (event == QStringLiteral("progress") && m_real &&
                ((m_phase == Connecting && state == QStringLiteral("initializing")) ||
                 (m_phase == Running && operation == m_operationId && id == operation))) {
            m_status->setText(QStringLiteral("状态：") + text);
            log(QStringLiteral("[语音] ") + text); return;
        }
        if (event == QStringLiteral("ready") && m_phase == Connecting && state == QStringLiteral("idle")) {
            m_startupTimer->stop();
            m_badge->setText(m_real ? QStringLiteral("麦克风已就绪 · 真实识别") : QStringLiteral("Python 已连接 · 模拟识别"));
            setPhase(Idle, m_real ? text : QStringLiteral("就绪，可以开始通信演示"));
            log(QStringLiteral("[Python → Qt] ") + text); return;
        }
        const bool isReply = !m_pendingId.isEmpty() && id == m_pendingId;
        const bool isSaveReply = !m_saveRequestId.isEmpty() && id == m_saveRequestId;
        const bool isCurrent = !m_operationId.isEmpty() && operation == m_operationId;
        if (m_real && isCurrent && id == operation && state == QStringLiteral("pending") &&
                m_phase == Pending && m_pendingId.isEmpty()) {
            if (event == QStringLiteral("confirmation_progress")) {
                m_status->setText(QStringLiteral("状态：") + text);
                log(QStringLiteral("[语音确认] ") + text);
                return;
            }
            if (event == QStringLiteral("voice_confirm")) {
                log(QStringLiteral("[语音确认] ") + text);
                sendRequest(QStringLiteral("confirm"));
                return;
            }
        }
        if (event == QStringLiteral("state") && isReply && isCurrent &&
                (m_pendingAction == QStringLiteral("start") || m_pendingAction == QStringLiteral("calibrate")) && state == QStringLiteral("running")) {
            clearPending(); setPhase(Running, m_real ? QStringLiteral("正在准备本轮收音，可以取消") : QStringLiteral("Python 正在模拟识别，可以取消"));
            m_operationTimer->start(m_real ? 120000 : 30000);
            log(QStringLiteral("[Python → Qt] ") + text);
        } else if (event == QStringLiteral("state") && isReply && isCurrent &&
                   m_pendingAction == QStringLiteral("confirm") && state == QStringLiteral("saving")) {
            m_saveRequestId = m_pendingId;
            clearPending();
            setPhase(Saving, text);
            m_operationTimer->start(60000);
            log(QStringLiteral("[Python → Qt] ") + text);
        } else if (event == QStringLiteral("calibration_result") && isCurrent && id == operation &&
                   state == QStringLiteral("idle") && m_phase == Running) {
            clearPending(); m_operationTimer->stop(); m_operationId.clear();
            m_result->setText(text);
            m_command->setText(message.value(QStringLiteral("summary")).toString());
            setPhase(Idle, message.value(QStringLiteral("success")).toBool()
                     ? QStringLiteral("检测设置已应用，可以开始识别") : QStringLiteral("检测未通过，可重试"));
            log(QStringLiteral("[语音检测] ") + text + QStringLiteral("\n") + message.value(QStringLiteral("summary")).toString());
        } else if (event == QStringLiteral("result") && isCurrent && id == operation &&
                   state == QStringLiteral("pending") && (m_phase == Running || m_phase == Pending)) {
            if (!message.value(QStringLiteral("simulated")).isBool() ||
                    message.value(QStringLiteral("simulated")).toBool() == m_real ||
                    !message.value(QStringLiteral("command")).isObject()) {
                failBackend(QStringLiteral("后台识别结果格式错误。")); return;
            }
            m_operationTimer->stop();
            m_result->setText((m_real ? QStringLiteral("识别文字：") : QStringLiteral("模拟识别文字：")) + message.value(QStringLiteral("text")).toString());
            m_command->setText(message.value(QStringLiteral("summary")).toString());
            setPhase(Pending, m_real ? QStringLiteral("核对后点击“确认保存”，或说“确认”")
                                    : QStringLiteral("Python 已返回结果，等待确认"));
            m_spectrumPath = message.value(QStringLiteral("spectrum_image_path")).toString();
            m_viewSpectrum->setEnabled(!m_spectrumPath.isEmpty());
            log(QStringLiteral("[Python → Qt] ") + text);
        } else if (event == QStringLiteral("rejected") && m_real && isCurrent && id == operation &&
                   state == QStringLiteral("idle") && m_phase == Running) {
            clearPending(); m_operationTimer->stop(); m_operationId.clear();
            m_result->setText(QStringLiteral("识别文字：") + message.value(QStringLiteral("text")).toString());
            m_command->setText(text);
            setPhase(Idle, QStringLiteral("本轮未通过检查，请重新开始"));
            log(QStringLiteral("[语音] ") + text);
        } else if ((event == QStringLiteral("confirmed") || event == QStringLiteral("cancelled")) &&
                   (isReply || isSaveReply) && isCurrent && state == QStringLiteral("idle") &&
                   ((event == QStringLiteral("confirmed") && (isSaveReply || m_pendingAction == QStringLiteral("confirm"))) ||
                    (event == QStringLiteral("cancelled") && m_pendingAction == QStringLiteral("cancel")))) {
            clearPending(); m_saveRequestId.clear(); m_operationTimer->stop(); m_operationId.clear();
            if (event == QStringLiteral("cancelled")) {
                m_result->setText(QStringLiteral("本轮已取消。")); m_command->clear();
            } else {
                const QString effect = message.value(QStringLiteral("effect")).toString();
                if (m_real && effect != QStringLiteral("record_saved") && effect != QStringLiteral("record_updated")) {
                    failBackend(QStringLiteral("后台未返回实际保存成功结果，请检查版本。")); return;
                }
                m_command->setText(m_real ? (effect == QStringLiteral("record_updated") ?
                    QStringLiteral("已更新（%1）：").arg(message.value(QStringLiteral("record")).toObject().value(QStringLiteral("status")).toString())
                    : QStringLiteral("已保存：")) +
                    message.value(QStringLiteral("record")).toObject().value(QStringLiteral("content")).toString() +
                    QStringLiteral("。可切换到历史记录查看。") : QStringLiteral("本轮已确认（通信演示），未保存真实实验记录。"));
                if (m_real) requestHistory(0);
            }
            setPhase(Idle, QStringLiteral("本轮结束，可以再次开始"));
            log(QStringLiteral("[Python → Qt] ") + text);
        } else if (event == QStringLiteral("error") && (isReply || isSaveReply || (isCurrent && id == operation))) {
            clearPending();
            if (isSaveReply) { m_saveRequestId.clear(); m_operationTimer->stop(); }
            if (state == QStringLiteral("idle")) {
                m_operationTimer->stop(); m_operationId.clear();
                m_result->setText(QStringLiteral("本轮未完成，请重新开始。")); m_command->clear();
                setPhase(Idle, text);
            } else if (isCurrent && (state == QStringLiteral("running") || state == QStringLiteral("pending"))) {
                setPhase(state == QStringLiteral("running") ? Running : Pending, text);
            } else { failBackend(QStringLiteral("后台状态与当前轮次不一致，请重新连接。")); return; }
            log(QStringLiteral("[Python → Qt] ") + text);
        } else {
            // Late or mismatched replies must never enable a confirmation.
            log(QStringLiteral("[通信] 已忽略不属于当前请求的消息。"));
        }
    }
};

int main(int argc, char *argv[])
{
    const bool render = argc == 4 && QByteArray(argv[1]) == "--render-spectrum";
    if (render) qputenv("QT_QPA_PLATFORM", "offscreen");
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("LabMate Assistant"));
    app.setApplicationVersion(QString::fromLatin1("LABMATE_UI_RECORDS_V2"));
    app.setProperty("imagePreviewVersion", QString::fromLatin1("LABMATE_UI_IMAGE_PREVIEW_V1"));
    app.setProperty("voiceConfirmVersion", QString::fromLatin1("LABMATE_UI_VOICE_CONFIRM_V1"));
    app.setProperty("recordEditVersion", QString::fromLatin1("LABMATE_UI_RECORD_EDIT_V1"));
    app.setProperty("voiceCalibrationVersion", QString::fromLatin1("LABMATE_UI_VOICE_CALIBRATION_V1"));
    app.setProperty("fftVersion", QString::fromLatin1("LABMATE_UI_FFT_V1"));
    app.setProperty("responseVersion", QString::fromLatin1("LABMATE_UI_RESPONSE_V1"));
    if (render) return renderSpectrum(QString::fromLocal8Bit(argv[2]), QString::fromLocal8Bit(argv[3])) ? 0 : 2;
    app.setFont(QFont(QStringLiteral("Noto Sans CJK SC"), 10));
    AssistantWindow window;
    window.show();
    return app.exec();
}
