#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QApplication>
#include <QDir>
#include <QTextCodec>
#include <QLabel>
#include <QDateTime>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkRequest>
#include <QtNetwork/QNetworkReply>
#include <QFile>
#include <QSocketNotifier>
#include <QTimer>
#include <QButtonGroup>

#include <stdlib.h>
#include <unistd.h>
#include <linux/input.h>

#include "qtpushbutton.h"
#include "qtprocess.h"
#include "qtwidget.h"


struct top_menu {
    QWidget *p;
    QLabel *title;
    QLabel *time;
};

struct weather_component {
    QWidget *p;
    QLabel *time;
    QLabel *date;
    QLabel *week;
    QLabel *icon;
    QLabel *temp;
    QLabel *city;
};

struct music_component {
    QWidget *p;
    QLabel *singerPhoto;
    QLabel *songName;
    QLabel *singerName;
    QPushButton *btnPre;
    QPushButton *btnPlay;
    QPushButton *btnNext;
};

struct key_monitor {
    QFile keyDev;
    QSocketNotifier* keySn;
    QTimer *timer;
};

struct app_type {
    QtPushButton *btn;
    QtProcess *pro;
    QString path;
};


class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = 0);
    ~MainWindow();

private slots:
    void slotBtnPreClicked(void);
    void slotBtnPlayClicked(void);
    void slotBtnNextClicked(void);

    void slotGetOnlineTimeFinished(void);

    void slotKeySnActivated(int);
    void slotKeyMonitorTimeout(void);

    void slotAppBtnClicked(int);

    void slotAppReadyRead(int id);
    void slotError(QProcess::ProcessError);
    void slotFinished(int,QProcess::ExitStatus);
    void slotStarted(void);
    void slotStateChanged(QProcess::ProcessState);

    void slotAppPageChanged(int index);

    void slotTimerTimeout(void);

private:
    struct top_menu topMenu;
    struct weather_component weatherComponent;
    struct music_component musicComponent;
    struct key_monitor keyMonitor;
    struct app_type apps[20];

    QLabel *logo;
    QDateTime dateTime;
    QTimer *timer;
    QNetworkAccessManager *NAManager;
    QNetworkReply *reply;

    QButtonGroup *group;
    QtWidget *appsP;
    QPropertyAnimation *animation;

    QLabel *indexBars[4];
    int currentPage;

    void initTopMenuBar(void);
    void initWeatherComponent(void);
    void initMusicComponent(void);
    void initBottomLogoShow(void);
    void getOnlineTimeDate(void);
    void initKeyMonitor(void);
    void initAppComponent(void);
    void initPageIndexBar(void);
    void initLabmateEntry(void);
    QProcess *labmateProcess;
};

#endif // MAINWINDOW_H
