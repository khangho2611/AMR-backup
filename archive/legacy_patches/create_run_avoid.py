target = '/home/khangho/rplidar_c1_test/app/run_avoidance.py'
code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rclpy
from autonomous_avoidance import AutonomousAvoidanceNode

def main():
    rclpy.init()
    node = AutonomousAvoidanceNode()
    node.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
'''
with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

print("CREATED run_avoidance.py!")
