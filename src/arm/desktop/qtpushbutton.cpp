#include "qtpushbutton.h"

QtPushButton::QtPushButton(QWidget *parent, QPropertyAnimation *a)
    : QPushButton(parent), p(parent), animation(a)
{
    mouseMove = false;
}

void QtPushButton::mousePressEvent(QMouseEvent *e)
{
    m_startPosY = e->globalX();
    this->resize(150, 107);
    QPushButton::mousePressEvent(e);
}

void QtPushButton::mouseMoveEvent(QMouseEvent *e)
{
    if (QPropertyAnimation::Running == animation->state())
        animation->stop();

    int nMoveEndY = e->globalX();
    int nOffset = m_startPosY - nMoveEndY;

    int nValue = p->pos().x();
    nValue -= nOffset;
    if (nValue > 100) nValue = 100;
    else if (nValue < -2500) nValue = -2500;

    p->move(nValue, 260);
    m_startPosY = nMoveEndY;
    mouseMove = true;
    QPushButton::mouseMoveEvent(e);
}

void QtPushButton::mouseReleaseEvent(QMouseEvent *e)
{
    if (mouseMove) {
        m_startPosY = p->pos().x();

        if (400 >= m_startPosY && -400 < m_startPosY) {
            animation->setEndValue(QPoint(0, 260));
            emit sigPageChanged(0);
        }
        else if (-400 >= m_startPosY && -1200 < m_startPosY) {
            animation->setEndValue(QPoint(-800, 260));
            emit sigPageChanged(1);
        }
        else if (-1200 >= m_startPosY && -2000 < m_startPosY) {
            animation->setEndValue(QPoint(-1600, 260));
            emit sigPageChanged(2);
        }
        else if (-2000 >= m_startPosY && -2800 < m_startPosY) {
            animation->setEndValue(QPoint(-2400, 260));
            emit sigPageChanged(3);
        }

        animation->setStartValue(QPoint(m_startPosY, 260));
        animation->start();
    }
    else
        QPushButton::mouseReleaseEvent(e);

    this->resize(140, 100);
    mouseMove = false;
}
