#ifndef QTPROCESS_H
#define QTPROCESS_H

#include <QProcess>

class QtProcess : public QProcess
{
    Q_OBJECT

public:
    explicit QtProcess(QObject *parent = Q_NULLPTR, int id = 0);

signals:
    void sigReadyRead(int id);

private slots:
    void slotReadyRead(void);

private:
    const int numId;
};

#endif // QTPROCESS_H
