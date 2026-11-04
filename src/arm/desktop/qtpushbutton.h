#ifndef QTPUSHBUTTON_H
#define QTPUSHBUTTON_H

#include <QPushButton>
#include <QMouseEvent>
#include <QPropertyAnimation>


class QtPushButton : public QPushButton
{
    Q_OBJECT

public:
    QtPushButton(QWidget *parent, QPropertyAnimation *a);
    ~QtPushButton() {}

private:
    bool mouseMove;
    int m_startPosY;
    QWidget *p;
    QPropertyAnimation *animation;

signals:
    void sigPageChanged(int index);

protected:
    virtual void mousePressEvent(QMouseEvent *e);
    virtual void mouseMoveEvent(QMouseEvent *e);
    virtual void mouseReleaseEvent(QMouseEvent *e);
};

#endif // QTPUSHBUTTON_H
