#include "qtprocess.h"

QtProcess::QtProcess(QObject *parent, int id)
    : QProcess(parent), numId(id)
{
    connect(this, SIGNAL(readyRead()), this, SLOT(slotReadyRead()));
}

void QtProcess::slotReadyRead()
{
    emit sigReadyRead(numId);
}
