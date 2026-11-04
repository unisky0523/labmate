#include "mainwindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setProperty("labmateDesktopVersion", QString::fromLatin1("LABMATE_DESKTOP_ENTRY_V1"));
    QDir::setCurrent(QCoreApplication::applicationDirPath());
    QTextCodec::setCodecForLocale(QTextCodec::codecForName("UTF-8"));
    MainWindow mainWindow;
    mainWindow.show();

    return app.exec();
}
