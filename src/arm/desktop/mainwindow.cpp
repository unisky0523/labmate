#include "mainwindow.h"
#include <QMessageBox>

#define BEIJING_TIME_API "http://quan.suning.com/getSysTime.do"

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    /* 主窗口初始化 */
    this->setGeometry(0, 0, 800, 480);              // 800x480 LCD
    this->setWindowFlags(Qt::FramelessWindowHint);  // 无边框
    this->setStyleSheet("QMainWindow{ background-image:url(./resources/image/background_1.png); }"); // 设置背景

    /* 初始化顶部菜单栏 */
    initTopMenuBar();

    /* 初始化天气组件 */
    initWeatherComponent();

    /* 初始化音乐组件 */
    initMusicComponent();

    /* 初始化app组件 */
    initAppComponent();

    /* 初始化页标控件 */
    initPageIndexBar();

    /* 初始化底部logo */
    initBottomLogoShow();
    initLabmateEntry();

    /* 获取在线时间 */
    getOnlineTimeDate();

    /* 按键监视初始化 */
    initKeyMonitor();
}

MainWindow::~MainWindow()
{
}

void MainWindow::initTopMenuBar(void)
{
    topMenu.p = new QWidget(this);
    topMenu.p->setGeometry(0, 0, 800, 40);
    topMenu.p->setStyleSheet("QWidget{ background-color:rgba(0, 0, 0, 80%); }");

    dateTime = QDateTime::currentDateTime();

    topMenu.title = new QLabel(topMenu.p);
    topMenu.title->setGeometry(350, 0, 100, 40);
    topMenu.title->setAlignment(Qt::AlignCenter);
    topMenu.title->setStyleSheet("QLabel{ background:transparent; color:#FFFFFF; font:20pt \"wqy-zenhei\"; }");
    topMenu.title->setText("主界面");

    topMenu.time = new QLabel(topMenu.p);
    topMenu.time->setGeometry(10, 0, 100, 40);
    topMenu.time->setAlignment(Qt::AlignCenter);
    topMenu.time->setStyleSheet("QLabel{ background:transparent; color:#38C5F9; font:18pt \"wqy-zenhei\"; }");
    topMenu.time->setText(dateTime.toString("HH:mm"));

    timer = new QTimer(this);
    connect(timer, SIGNAL(timeout()), this, SLOT(slotTimerTimeout()));
    timer->start(1000);
}

void MainWindow::initWeatherComponent(void)
{
    weatherComponent.p = new QWidget(this);
    weatherComponent.p->setGeometry(20, 60, 370, 180);
    weatherComponent.p->setStyleSheet("QWidget{ background-color:rgba(0, 0, 0, 80%);"
                                      "         border-radius:10px; }");

    /* 时间 */
    weatherComponent.time = new QLabel(weatherComponent.p);
    weatherComponent.time->setGeometry(0, 0, 200, 100);
    weatherComponent.time->setStyleSheet("QLabel{ background-color:transparent;"
                                         "        color:#FFFFFF; font:54pt \"wqy-zenhei\"; }");
    weatherComponent.time->setText(dateTime.toString("HH:mm"));
    weatherComponent.time->setAlignment(Qt::AlignRight | Qt::AlignVCenter);

    /* 日期 */
    weatherComponent.date = new QLabel(weatherComponent.p);
    weatherComponent.date->setGeometry(0, 100, 200, 40);
    weatherComponent.date->setStyleSheet("QLabel{ background-color:transparent;"
                                         "        color:#FFFFFF; font:18pt \"wqy-zenhei\"; }");
    weatherComponent.date->setText(dateTime.toString("yyyy-MM-dd"));
    weatherComponent.date->setAlignment(Qt::AlignRight | Qt::AlignBottom);

    /* 星期 */
    weatherComponent.week = new QLabel(weatherComponent.p);
    weatherComponent.week->setGeometry(0, 140, 200, 40);
    weatherComponent.week->setStyleSheet("QLabel{ background-color:transparent;"
                                         "        color:#FFFFFF; font:18pt \"wqy-zenhei\"; }");
    weatherComponent.week->setText(dateTime.toString("dddd"));
    weatherComponent.week->setAlignment(Qt::AlignRight | Qt::AlignTop);

    /* 天气图标 */
    weatherComponent.icon = new QLabel(weatherComponent.p);
    weatherComponent.icon->setGeometry(250, 15, 70, 70);
    weatherComponent.icon->setScaledContents(true);
    weatherComponent.icon->setStyleSheet("QLabel{ background-color:transparent; }");
    QPixmap pixmap("./apps/1/resources/icon/weather_icon/晴.png");
    weatherComponent.icon->setPixmap(pixmap);

    /* 温度 */
    weatherComponent.temp = new QLabel(weatherComponent.p);
    weatherComponent.temp->setGeometry(250, 100, 70, 40);
    weatherComponent.temp->setStyleSheet("QLabel{ background-color:transparent;"
                                         "        color:#FFFFFF; font:18pt \"wqy-zenhei\" }");
    weatherComponent.temp->setText("25°C");
    weatherComponent.temp->setAlignment(Qt::AlignHCenter | Qt::AlignBottom);

    /* 城市 */
    weatherComponent.city = new QLabel(weatherComponent.p);
    weatherComponent.city->setGeometry(230, 140, 110, 40);
    weatherComponent.city->setStyleSheet("QLabel{ background-color:transparent;"
                                         "        color:#FFFFFF; font:18pt \"wqy-zenhei\" }");
    weatherComponent.city->setText("正点原子");
    weatherComponent.city->setAlignment(Qt::AlignHCenter | Qt::AlignTop);
}

void MainWindow::initMusicComponent(void)
{
    musicComponent.p = new QWidget(this);
    musicComponent.p->setGeometry(410, 60, 370, 180);
    musicComponent.p->setStyleSheet("QWidget{ background-color:rgba(0, 0, 0, 80%);"
                                    "         border-radius:10px; }");

    /* 歌手照片 */
    musicComponent.singerPhoto = new QLabel(musicComponent.p);
    musicComponent.singerPhoto->setGeometry(10, 50, 120, 120);
    musicComponent.singerPhoto->setStyleSheet("QLabel{ background-color:transparent; }");
    musicComponent.singerPhoto->setScaledContents(true);
    QPixmap pixmap("./apps/0/resources/image/singer_photo.png");
    musicComponent.singerPhoto->setPixmap(pixmap);

    /* 歌曲名 */
    musicComponent.songName = new QLabel(musicComponent.p);
    musicComponent.songName->setGeometry(0, 0, 370, 40);
    musicComponent.songName->setAlignment(Qt::AlignHCenter | Qt::AlignBottom);
    musicComponent.songName->setStyleSheet("QLabel{ background-color:transparent;"
                                             "        color:#FFFFFF; font:16pt \"wqy-zenhei\"; }");
    musicComponent.songName->setText("请先打开音乐播放器...");

    /* 歌手名 */
    musicComponent.singerName = new QLabel(musicComponent.p);
    musicComponent.singerName->setGeometry(180, 55, 200, 50);
    musicComponent.singerName->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    musicComponent.singerName->setStyleSheet("QLabel{ background-color:transparent;"
                                             "        color:#FFFFFF; font:16pt \"wqy-zenhei\"; }");
    musicComponent.singerName->setText("未知");

    /* 按钮(上一首) */
    musicComponent.btnPre = new QPushButton(musicComponent.p);
    musicComponent.btnPre->setGeometry(170, 105, 50, 50);
    musicComponent.btnPre->setStyleSheet("QPushButton{ border-image:url(:resources/icon/last_2.png);"
                                         "             background-color:transparent; outline: none; }"
                                         "QPushButton:pressed{ border-image:url(:resources/icon/last_1.png); }");

    /* 按钮(播放/暂停) */
    musicComponent.btnPlay = new QPushButton(musicComponent.p);
    musicComponent.btnPlay->setGeometry(240, 105, 50, 50);
    musicComponent.btnPlay->setStyleSheet("QPushButton{ border-image:url(:resources/icon/play_2.png);"
                                          "             background-color:transparent; outline: none; }"
                                          "QPushButton:pressed{ border-image:url(:resources/icon/play_1.png); }");

    /* 按钮(下一首) */
    musicComponent.btnNext = new QPushButton(musicComponent.p);
    musicComponent.btnNext->setGeometry(310, 105, 50, 50);
    musicComponent.btnNext->setStyleSheet("QPushButton{ border-image:url(:resources/icon/next_2.png);"
                                          "             background-color:transparent; outline: none; }"
                                          "QPushButton:pressed{ border-image:url(:resources/icon/next_1.png); }");

    /* 按钮信号槽连接 */
    connect(musicComponent.btnPre, SIGNAL(clicked()), this, SLOT(slotBtnPreClicked()));
    connect(musicComponent.btnPlay, SIGNAL(clicked()), this, SLOT(slotBtnPlayClicked()));
    connect(musicComponent.btnNext, SIGNAL(clicked()), this, SLOT(slotBtnNextClicked()));
}

void MainWindow::initBottomLogoShow(void)
{
    logo = new QLabel(this);
    logo->setGeometry(0, 390, 800, 90);
    QPixmap pixmap("./apps/19/resources/image/logo.png");
    logo->setPixmap(pixmap);
}

void MainWindow::initLabmateEntry(void)
{
    auto *entry = new QPushButton(QString::fromUtf8("实验助手"), this);
    entry->setObjectName(QStringLiteral("labmateEntry"));
    entry->setGeometry(610, 400, 170, 60);
    entry->setStyleSheet(QStringLiteral(
        "QPushButton {background:#1763c0; color:white; border:2px solid #70b5ff;"
        "border-radius:12px; font:22px 'wqy-zenhei';}"
        "QPushButton:pressed {background:#355478;}"
        "QPushButton:disabled {background:#43526a;}"));
    labmateProcess = new QProcess(this);
    connect(entry, &QPushButton::clicked, this, [this, entry]() {
        if (labmateProcess->state() != QProcess::NotRunning) return;
        entry->setEnabled(false);
        labmateProcess->start(QStringLiteral("/bin/sh"),
            QStringList() << QStringLiteral("/home/root/labmate_ui_test/run_ui_desktop.sh"));
    });
    connect(labmateProcess, &QProcess::started, this, [this]() { hide(); });
    connect(labmateProcess, &QProcess::errorOccurred, this,
            [this, entry](QProcess::ProcessError error) {
        if (error != QProcess::FailedToStart) return;
        entry->setEnabled(true);
        show(); raise(); activateWindow();
        QMessageBox::warning(this, QString::fromUtf8("实验助手"),
                             QString::fromUtf8("启动失败，请重试。"));
    });
    connect(labmateProcess,
            static_cast<void (QProcess::*)(int, QProcess::ExitStatus)>(&QProcess::finished),
            this, [this, entry](int exitCode, QProcess::ExitStatus status) {
        QFile log(QStringLiteral("/home/root/labmate_ui_test/desktop_launch.log"));
        if (log.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            log.write(labmateProcess->readAllStandardOutput().right(8192));
            log.write(labmateProcess->readAllStandardError().right(8192));
        }
        entry->setEnabled(true);
        show(); raise(); activateWindow(); update();
        if (exitCode != 0 || status != QProcess::NormalExit)
            QMessageBox::warning(this, QString::fromUtf8("实验助手"),
                QString::fromUtf8("实验助手未能正常运行。请先关闭占用录音或播放的其他应用，再重试。"));
    });
}

void MainWindow::getOnlineTimeDate(void)
{
    QNetworkRequest request;
    request.setUrl(QUrl(BEIJING_TIME_API));

    NAManager = new QNetworkAccessManager(this);
    reply = NAManager->get(request);
    connect(reply, SIGNAL(finished()), this, SLOT(slotGetOnlineTimeFinished()));
}

void MainWindow::initKeyMonitor(void)
{
    QFile f("/dev/input/event2");
    if (f.exists()) keyMonitor.keyDev.setFileName("/dev/input/event2");
    else keyMonitor.keyDev.setFileName("/dev/input/event1");

    keyMonitor.keyDev.open(QIODevice::ReadOnly);
    keyMonitor.keySn = new QSocketNotifier(keyMonitor.keyDev.handle(), QSocketNotifier::Read, this);
    connect(keyMonitor.keySn, SIGNAL(activated(int)), this, SLOT(slotKeySnActivated(int)));

    keyMonitor.timer = new QTimer(this);
    connect(keyMonitor.timer, SIGNAL(timeout()), this, SLOT(slotKeyMonitorTimeout()));
}

void MainWindow::initAppComponent(void)
{
    appsP = new QtWidget(this);
    appsP->setGeometry(0, 260, 3200, 100);
    appsP->setStyleSheet("QWidget{ background-color:transparent; }");

    animation = new QPropertyAnimation(appsP, "pos");
    animation->setDuration(500);
    animation->setEasingCurve(QEasingCurve::OutExpo);
    animation->setLoopCount(1);

    group = new QButtonGroup(this);
    connect(group, SIGNAL(buttonClicked(int)), this, SLOT(slotAppBtnClicked(int)));

    for (int i = 0; i < 20; i++) {

        apps[i].btn = new QtPushButton(appsP, animation);
        apps[i].pro = new QtProcess(appsP, i);
        apps[i].btn->setGeometry(20 + 155 * (i % 5) + 800 * (i / 5), 0, 140, 100);
        apps[i].path = "./apps/" + QString::number(i) + "/app";
        group->addButton(apps[i].btn, i);

        connect(apps[i].btn, SIGNAL(sigPageChanged(int)), this, SLOT(slotAppPageChanged(int)));
        connect(apps[i].pro, SIGNAL(sigReadyRead(int)), this, SLOT(slotAppReadyRead(int)));
        connect(apps[i].pro, SIGNAL(error(QProcess::ProcessError)), this, SLOT(slotError(QProcess::ProcessError)));
        connect(apps[i].pro, SIGNAL(finished(int,QProcess::ExitStatus)), this, SLOT(slotFinished(int,QProcess::ExitStatus)));
        connect(apps[i].pro, SIGNAL(started()), this, SLOT(slotStarted()));
        connect(apps[i].pro, SIGNAL(stateChanged(QProcess::ProcessState)), this, SLOT(slotStateChanged(QProcess::ProcessState)));
    }

    apps[0].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/musicPlay.png); outline:none; }");
    apps[1].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/onlineWeather.png); outline:none; }");
    apps[2].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/pictureView.png); outline:none; }");
    apps[3].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/camera.png); outline:none; }");
    apps[4].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/fileManager.png); outline:none; }");

    apps[5].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/clock.png); outline:none; }");
    apps[6].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/calendar.png); outline:none; }");
    apps[7].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/calculator.png); outline:none; }");
    apps[8].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/ebook.png); outline:none; }");
    apps[9].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/Notepad.png); outline:none; }");

    apps[10].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/keyTest.png); outline:none; }");
    apps[11].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/LED.png); outline:none; }");
    apps[12].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/ADC.png); outline:none; }");
    apps[13].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/temp.png); outline:none; }");
    apps[14].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/VoltageMonitoring.png); outline:none; }");

    apps[15].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/OpenCV.png); outline:none; }");
    apps[16].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/eluosifangkuai.png); outline:none; }");
    apps[17].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/QtDemo_1.png); outline:none; }");
    apps[18].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/QtDemo_2.png); outline:none; }");
    apps[19].btn->setStyleSheet("QPushButton{ border-image:url(:/resources/icon/appicon/systemSetting.png); outline:none; }");
}

void MainWindow::initPageIndexBar(void)
{
    QPixmap pixmap(":/resources/icon/bar_1.png");

    for (int i = 0; i < 4; i++) {

        indexBars[i] = new QLabel(this);
        indexBars[i]->setGeometry(316 + (38 + 5) * i, 370, 38, 6);
    }

    indexBars[1]->setPixmap(pixmap);
    indexBars[2]->setPixmap(pixmap);
    indexBars[3]->setPixmap(pixmap);

    currentPage = 0;
    pixmap.load(":/resources/icon/bar_2.png");
    indexBars[currentPage]->setPixmap(pixmap);
}

void MainWindow::slotBtnPreClicked(void)
{
    /* 这里0号app指的就是音乐播放器，这是人为定的，根据app排序来着
     * 首先判断app是否处于运行状态，如果没有运行的话 我们这里只能退出
     */
    if (QProcess::NotRunning == apps[0].pro->state())
        return;
    else
        apps[0].pro->write("prev", 10);        // 将消息发送给app让其进行处理
}

void MainWindow::slotBtnPlayClicked(void)
{
    if (QProcess::NotRunning == apps[0].pro->state())
        return;
    else
        apps[0].pro->write("play", 10);
}

void MainWindow::slotBtnNextClicked(void)
{
    if (QProcess::NotRunning == apps[0].pro->state())
        return;
    else
        apps[0].pro->write("next", 10);
}

void MainWindow::slotGetOnlineTimeFinished(void)
{
    QByteArray output = reply->readAll();
    reply->deleteLater();
    delete NAManager;

    if (output.isEmpty() || output.isNull())
        return;

    QByteArray timeDate = output.mid(13, output.indexOf("sysTime1") - 16);
    timeDate = "date -s \"" + timeDate + "\"";
    system(timeDate.data());
}

void MainWindow::slotKeySnActivated(int fd)
{
    struct input_event input_ev;
    if (fd != keyMonitor.keyDev.handle() || this->isHidden())
        return;

    if (read(fd, &input_ev, sizeof(input_ev)) == sizeof(input_ev)) {
        if (input_ev.type == EV_KEY) {
            if (input_ev.value == 0) {
                if(KEY_ENTER == input_ev.code) {
                    if (keyMonitor.timer->isActive()) {
                        keyMonitor.timer->stop();
                    }
                }
            }
            else {
                if(KEY_ENTER == input_ev.code) {
                    if (!keyMonitor.timer->isActive()) {
                        keyMonitor.timer->start(2000);
                    }
                }
            }
        }
    }
}

void MainWindow::slotKeyMonitorTimeout(void)
{
    disconnect(keyMonitor.keySn, SIGNAL(activated(int)), this, SLOT(slotKeySnActivated(int)));
    keyMonitor.timer->stop();

    for (int i = 0; i < 20; i++) {

        if (QProcess::NotRunning != apps[i].pro->state()) {
            apps[i].pro->write("quit", 10);
            apps[i].pro->waitForFinished(-1);
        }
    }

    this->hide();
    //qApp->quit();   // 退出时界面无法隐藏 TM的
    this->close();
}

void MainWindow::slotAppBtnClicked(int id)
{
    if (QProcess::NotRunning == apps[id].pro->state()) {
        apps[id].pro->start(apps[id].path); // 开始运行app
        apps[id].pro->waitForStarted(-1);   // 阻塞等待app运行开始
    }
    else {
        apps[id].pro->write("show", 10);        // 发送信息给app，让其显示
        this->hide();                       // 隐藏主界面
    }
}

void MainWindow::slotAppReadyRead(int id)
{
    QByteArray all = apps[id].pro->readAllStandardOutput();
    QString output = QString::fromStdString(all.toStdString());

    if (output == "show") {       // 收到app发来的显示信号，显示主界面
        this->show();
        return;
    }

    if (0 == id) {
        if (output.contains("play")) {
            int i = output.indexOf("song");
            int j = output.indexOf("singer");
            musicComponent.songName->setText(output.mid(i + 5, j - 1 - i - 5));
            musicComponent.singerName->setText(output.mid(j + 7, -1));

            musicComponent.btnPlay->setStyleSheet("QPushButton{ border-image:url(:resources/icon/stop_2.png);"
                                   "             background-color:transparent;"
                                   "             outline: none; }"
                                   "QPushButton:pressed{ border-image:url(:resources/icon/stop_1.png); }");
        }
        else if (output.contains("stop")) {
            musicComponent.btnPlay->setStyleSheet("QPushButton{ border-image:url(:resources/icon/play_2.png);"
                                   "             background-color:transparent;"
                                   "             outline: none; }"
                                   "QPushButton:pressed{ border-image:url(:resources/icon/play_1.png); }");
        }
    }
    else if (1 == id) {
        if (output.contains("update")) {
            int i = output.indexOf("city");
            int j = output.indexOf("temp");
            int k = output.indexOf("type");
            weatherComponent.city->setText(output.mid(i + 5, j - 1 - i - 5));
            weatherComponent.temp->setText(output.mid(j + 5, k - 1 - j - 5) + "℃");
            QString path = "./apps/1/resources/icon/weather_icon/" + output.mid(k + 5, -1) + ".png";
            QFileInfo file(path);
            if (false == file.exists())
                path = "./apps/1/resources/icon/weather_icon/未知.png";
            QPixmap pixmap(path);
            weatherComponent.icon->setPixmap(pixmap);
        }
    }
}

void MainWindow::slotError(QProcess::ProcessError error)
{
    switch (error) {
    case QProcess::FailedToStart:
    break;

    case QProcess::Crashed:
    break;

    case QProcess::Timedout:
    break;

    case QProcess::WriteError:
    break;

    case QProcess::ReadError:
    break;

    case QProcess::UnknownError:
    break;
    }
}

void MainWindow::slotFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    Q_UNUSED(exitCode);
    Q_UNUSED(exitStatus);
}

void MainWindow::slotStarted()
{
    /* 如果App已成功启动则隐藏主界面 */
    this->hide();
}

void MainWindow::slotStateChanged(QProcess::ProcessState newState)
{
    switch (newState) {
    case QProcess::NotRunning:
    break;

    case QProcess::Starting:
    break;

    case QProcess::Running:
    break;
    }
}

void MainWindow::slotAppPageChanged(int index)
{
    if (index == currentPage)
        return;

    QPixmap pixmap(":/resources/icon/bar_2.png");
    indexBars[index]->setPixmap(pixmap);

    pixmap.load(":/resources/icon/bar_1.png");
    indexBars[currentPage]->setPixmap(pixmap);

    currentPage = index;
}

void MainWindow::slotTimerTimeout(void)
{
    dateTime = QDateTime::currentDateTime();
    QString t = dateTime.toString("HH:mm");
    topMenu.time->setText(t);
    weatherComponent.date->setText(dateTime.toString("yyyy-MM-dd"));
    weatherComponent.time->setText(t);
    weatherComponent.week->setText(dateTime.toString("dddd"));
}
