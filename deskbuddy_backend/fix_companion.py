with open('app/services/companion.py', 'r') as f:
    content = f.read()

# Fix 1: inspection result send
old1 = """                    # Also send result back to device
                    # Send result back to device
                    from app.services import serial_manager as serial_state
                    manager = serial_state.get_serial_manager()
                    if manager and manager.is_connected:
                        await manager.send_command("inspection_result", result)"""
new1 = """                    # Also send result back to device
                    from app.services.hardware_bridge import hardware_bridge
                    if hardware_bridge.is_connected:
                        await hardware_bridge.send_command("inspection_result", result)"""
assert old1 in content, 'old1 not found'
content = content.replace(old1, new1)

# Fix 2: push_notification
old2 = """        from app.services import serial_manager as serial_state

        manager = serial_state.get_serial_manager()
        if not manager or not manager.is_connected:
            return False

        return await manager.send_command("""
new2 = """        from app.services.hardware_bridge import hardware_bridge

        if not hardware_bridge.is_connected:
            return False

        return await hardware_bridge.send_command("""
assert old2 in content, 'old2 not found'
content = content.replace(old2, new2)

with open('app/services/companion.py', 'w') as f:
    f.write(content)
print('Done')