#ifndef QTWIDGET_H
#define QTWIDGET_H

#include <QWidget>
#include <QMouseEvent>
#include <QPropertyAnimation>

class QtWidget : public QWidget
{
    Q_OBJECT

public:
    explicit QtWidget(QWidget *parent);

//private:
//    int m_startPosY;
//    bool mouseMove;
//    QPropertyAnimation *animation;

//protected:
//    virtual void mousePressEvent(QMouseEvent *e);
//    virtual void mouseMoveEvent(QMouseEvent *e);
//    virtual void mouseReleaseEvent(QMouseEvent *e);

//public:
//    void setAnimationObj(QPropertyAnimation *a);
};

#endif // QTWIDGET_H
