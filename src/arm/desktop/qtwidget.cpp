#include "qtwidget.h"

QtWidget::QtWidget(QWidget *parent)
    : QWidget(parent)
{
//    mouseMove = false;
}

//void QtWidget::setAnimationObj(QPropertyAnimation *a)
//{
//    animation = a;
//}

//void QtWidget::mousePressEvent(QMouseEvent *e)
//{
//    m_startPosY = e->globalX();
//    QWidget::mousePressEvent(e);
//}

//void QtWidget::mouseMoveEvent(QMouseEvent *e)
//{
//    if (QPropertyAnimation::Running == animation->state())
//        animation->stop();

//    int nMoveEndY = e->globalX();
//    int nOffset = m_startPosY - nMoveEndY;

//    int nValue = this->pos().x();
//    nValue -= nOffset;
//    if (nValue > 100) nValue = 100;
//    else if (nValue < -2500) nValue = -2500;

//    this->move(nValue, 260);
//    mouseMove = true;
//    m_startPosY = nMoveEndY;
//    QWidget::mouseMoveEvent(e);
//}

//void QtWidget::mouseReleaseEvent(QMouseEvent *e)
//{
//    if (mouseMove) {
//        m_startPosY = this->pos().x();

//        if (400 >= m_startPosY && -400 < m_startPosY)
//            animation->setEndValue(QPoint(0, 260));
//        else if (-400 >= m_startPosY && -1200 < m_startPosY)
//            animation->setEndValue(QPoint(-800, 260));
//        else if (-1200 >= m_startPosY && -2000 < m_startPosY)
//            animation->setEndValue(QPoint(-1600, 260));
//        else if (-2000 >= m_startPosY && -2800 < m_startPosY)
//            animation->setEndValue(QPoint(-2400, 260));

//        animation->setStartValue(QPoint(m_startPosY, 260));
//        animation->start();
//    }

//    QWidget::mouseReleaseEvent(e);
//}
