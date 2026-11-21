"""事件循环友好的询问框：返回 asyncio.Future，而不是阻塞式的 exec()。

服务端与面板共用 qasync 的同一个事件循环，模态对话框会让挂起期间的
网络请求停摆，所以这里统一用非模态 QMessageBox + Future。
"""
import asyncio

from PySide6.QtWidgets import QMessageBox


async def ask_yes_no(title: str, text: str, parent=None,
                     yes_text: str = "确认", no_text: str = "取消") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.button(QMessageBox.Yes).setText(yes_text)
    box.button(QMessageBox.No).setText(no_text)
    box.setDefaultButton(QMessageBox.No)

    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def on_finished(code: int) -> None:
        if not future.done():
            future.set_result(code == QMessageBox.Yes)

    box.finished.connect(on_finished)
    box.open()
    return await future
