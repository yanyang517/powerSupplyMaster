"""
SCPI 电源模拟器 - 用于测试的虚拟串口设备

该脚本模拟一个真实的 SCPI 电源设备，通过虚拟串口与主程序通信。
支持常见的 SCPI 命令，如电压设置/查询、电流设置/查询等。

使用方法：
1. 安装 pyserial-protocol 包（可选，用于更高级的模拟）
2. 运行脚本创建虚拟串口
3. 主程序连接到指定的虚拟串口端口

Windows 环境需要先安装虚拟串口驱动：
- com0com: https://sourceforge.net/projects/com0com/
- VSPE: https://www.eterlogic.com/Products.VSPE.html
"""

import asyncio
import serial
import serial_asyncio
import logging
import time
import math
import random
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SCPISimulator:
    """SCPI 电源模拟器"""
    
    def __init__(self, port: str = 'COM4', baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.is_running = False
        
        # 设备状态
        self.voltage: float = 12.0  # 当前电压 (V)
        self.current: float = 0.0  # 当前电流 (A)
        self.power: float = 0.0    # 当前功率 (W)
        self.output_enabled: bool = False  # 输出开关状态
        
        # 保护限制
        self.max_voltage: float = 20.0  # 最大电压限制 (V)
        self.max_current: float = 3.0   # 最大电流限制 (A)
        
        # 通道配置
        self.channels: int = 3  # 3 通道电源
        self.channel_voltages: list = [0.0, 0.0, 0.0]
        self.channel_currents: list = [0.0, 0.0, 0.0]
        
        # 串口对象
        self.serial_server = None
    
    async def start(self):
        """启动串口服务器"""
        try:
            # 在 Windows 上，需要使用虚拟串口软件创建配对串口
            # 例如：COM3 <-> COM4
            # 这里我们监听指定的串口
            
            # 注意：Python 的 serial_asyncio 不直接支持作为服务器端
            # 我们需要使用轮询方式或第三方库
            
            logger.info(f"Starting SCPI simulator on {self.port} at {self.baudrate} baud")
            logger.info("Note: Make sure virtual serial port is created first!")
            
            # 尝试打开串口（作为客户端连接虚拟串口对）
            try:
                self.serial_conn = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1
                )
                logger.info(f"✅ Connected to {self.port}")
                
                # 开始处理串口数据
                await self.process_serial()
                
            except serial.SerialException as e:
                logger.error(f"❌ Failed to open {self.port}: {e}")
                logger.info("Please create virtual serial port pair first:")
                logger.info("  Windows: Use com0com or VSPE")
                logger.info("  Linux: Use socat or tty0tty")
                raise
                
        except Exception as e:
            logger.error(f"Error starting simulator: {e}", exc_info=True)
            raise
    
    async def process_serial(self):
        """处理串口数据"""
        self.is_running = True
        buffer = b''
        
        while self.is_running:
            try:
                if self.serial_conn.in_waiting > 0:
                    # 读取数据
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer += data
                    
                    logger.debug(f"Received: {data!r}")
                    
                    # 处理完整的 SCPI 命令（以换行符结束）
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        command = line.decode('utf-8').strip()
                        
                        if command:
                            logger.info(f"SCPI Command: {command}")
                            response = await self.execute_scpi_command(command)
                            
                            if response:
                                # 发送响应
                                response_bytes = (response + '\n').encode('utf-8')
                                self.serial_conn.write(response_bytes)
                                logger.debug(f"Sent: {response_bytes!r}")
                
                # 短暂等待，避免 CPU 占用过高
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error processing serial: {e}", exc_info=True)
                break
        
        self.stop()
    
    async def execute_scpi_command(self, command: str) -> str:
        """执行 SCPI 命令并返回响应"""
        cmd = command.strip()
        
        # 通用命令
        if cmd == '*IDN?':
            return self.handle_ident()
        elif cmd == '*RST':
            return self.handle_reset()
        elif cmd == '*CLS':
            return self.handle_clear()
        elif cmd.startswith('*'):
            return self.handle_system_command(cmd)
        
        # 电压相关命令
        elif cmd == 'MEASure:VOLTage?':
            if random.choice([True, False]):
                voltage = self.voltage + random.uniform(-0.1, 0.1)
            else:
                voltage = self.voltage
            return f"{voltage:.2f}"
        elif cmd.startswith('VOLTage '):
            voltage = float(cmd.split()[1])
            return self.set_voltage(voltage)
        elif cmd == 'VOLT:PROT?':
            return f"{self.max_voltage:.3f}"
        elif cmd.startswith('VOLT:PROT '):
            max_volt = float(cmd.split()[1])
            return self.set_max_voltage(max_volt)
        
        # 电流相关命令
        elif cmd == 'MEASure:CURRent?':
            self.current = (math.sin(time.time()) + 1) / 2 * self.max_current
            return f"{self.current:.3f}"
        elif cmd.startswith('CURR '):
            current = float(cmd.split()[1])
            return self.set_current(current)
        elif cmd == 'CURR:PROT?':
            return f"{self.max_current:.2f}"
        elif cmd.startswith('CURR:PROT '):
            max_curr = float(cmd.split()[1])
            return self.set_max_current(max_curr)
        
        # 功率查询
        elif cmd == 'POW?':
            return f"{self.power:.2f}"
        
        # 输出控制
        elif cmd == 'OUTP?':
            return 'ON' if self.output_enabled else 'OFF'
        elif cmd == 'OUTP ON':
            return self.set_output(True)
        elif cmd == 'OUTP OFF':
            return self.set_output(False)
        
        # 状态查询
        elif cmd == 'STAT?':
            return self.get_status()
        
        # 未知命令
        else:
            logger.warning(f"Unknown command: {cmd}")
            return 'ERROR: Unknown command'
    
    def handle_ident(self) -> str:
        """*IDN? - 返回设备标识"""
        return "FAKE,RIGOL DP832,SN888888888,VER00.00.00.00"
    
    def handle_reset(self) -> str:
        """*RST - 重置设备"""
        self.voltage = 0.0
        self.current = 0.0
        self.power = 0.0
        self.output_enabled = False
        logger.info("Device reset")
        return 'OK'
    
    def handle_clear(self) -> str:
        """*CLS - 清除状态寄存器"""
        return 'OK'
    
    def handle_system_command(self, cmd: str) -> str:
        """处理其他系统命令"""
        logger.info(f"System command: {cmd}")
        return 'OK'
    
    def set_voltage(self, voltage: float) -> str:
        """设置电压"""
        if voltage < 0 or voltage > self.max_voltage:
            return f'ERROR: Voltage out of range (0-{self.max_voltage}V)'
        
        self.voltage = voltage
        self.power = self.voltage * self.current
        logger.info(f"Voltage set to: {voltage:.2f}V")
        return 'OK'
    
    def set_current(self, current: float) -> str:
        """设置电流"""
        if current < 0 or current > self.max_current:
            return f'ERROR: Current out of range (0-{self.max_current}A)'
        
        self.current = current
        self.power = self.voltage * self.current
        logger.info(f"Current set to: {current:.2f}A")
        return 'OK'
    
    def set_max_voltage(self, max_voltage: float) -> str:
        """设置最大电压保护"""
        if max_voltage < 0:
            return 'ERROR: Invalid max voltage'
        
        self.max_voltage = max_voltage
        logger.info(f"Max voltage limit set to: {max_voltage:.3f}V")
        return 'OK'
    
    def set_max_current(self, max_current: float) -> str:
        """设置最大电流保护"""
        if max_current < 0:
            return 'ERROR: Invalid max current'
        
        self.max_current = max_current
        logger.info(f"Max current limit set to: {max_current:.3f}A")
        return 'OK'
    
    def set_output(self, enabled: bool) -> str:
        """控制输出开关"""
        self.output_enabled = enabled
        logger.info(f"Output {'enabled' if enabled else 'disabled'}")
        return 'OK'
    
    def get_status(self) -> str:
        """获取设备状态"""
        # 返回格式：操作状态，事件状态，错误状态
        operational = 1 if self.output_enabled else 0
        event = 0
        error = 0
        return f"{operational},{event},{error}"
    
    def stop(self):
        """停止模拟器"""
        self.is_running = False
        if hasattr(self, 'serial_conn') and self.serial_conn:
            self.serial_conn.close()
            logger.info("Serial connection closed")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SCPI Power Supply Simulator')
    parser.add_argument('--port', type=str, default='COM9', help='Virtual serial port (default: COM4)')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate (default: 115200)')
    
    args = parser.parse_args()
    
    simulator = SCPISimulator(port=args.port, baudrate=args.baud)
    
    try:
        await simulator.start()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    finally:
        simulator.stop()


if __name__ == '__main__':
    asyncio.run(main())
