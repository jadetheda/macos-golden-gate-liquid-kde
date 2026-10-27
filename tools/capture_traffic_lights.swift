import Cocoa
import CoreGraphics
import Foundation

// Ensure standard Cocoa application environment
let app = NSApplication.shared
app.setActivationPolicy(.regular)

let osVersion = ProcessInfo.processInfo.operatingSystemVersion
print("macOS System Version: \(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)")

let outputDir = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "./traffic_captures")
try? FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)

// Helper: Save an NSImage or CGImage to PNG file
func saveCGImage(_ cgImage: CGImage, to filename: String) {
    let url = outputDir.appendingPathComponent(filename)
    let rep = NSBitmapImageRep(cgImage: cgImage)
    guard let data = rep.representation(using: .png, properties: [:]) else {
        print("Failed to encode PNG for \(filename)")
        return
    }
    do {
        try data.write(to: url)
        print("Saved: \(filename) (\(cgImage.width)x\(cgImage.height))")
    } catch {
        print("Error saving \(filename): \(error)")
    }
}

// Function to set system appearance via AppleScript
func setDarkMode(_ dark: Bool) {
    let script = "tell application \"System Events\" to tell appearance preferences to set dark mode to \(dark ? "true" : "false")"
    if let appleScript = NSAppleScript(source: script) {
        var error: NSDictionary?
        appleScript.executeAndReturnError(&error)
        if let err = error {
            print("AppleScript appearance error: \(err)")
        }
    }
    Thread.sleep(forTimeInterval: 1.0)
}

// Capture on-screen region using macOS screencapture CLI
func captureRect(_ rect: CGRect, filename: String) {
    let url = outputDir.appendingPathComponent(filename)
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    let x = max(0, Int(rect.origin.x))
    let y = max(0, Int(rect.origin.y))
    let w = max(1, Int(rect.size.width))
    let h = max(1, Int(rect.size.height))
    process.arguments = ["-x", "-R\(x),\(y),\(w),\(h)", url.path]
    try? process.run()
    process.waitUntilExit()
    print("Captured rect \(x),\(y),\(w),\(h) to \(filename)")
}

// Post mouse events
func moveMouse(to pt: CGPoint) {
    let ev = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: pt, mouseButton: .left)
    ev?.post(tap: .cghidEventTap)
    Thread.sleep(forTimeInterval: 0.25)
}

func leftDown(at pt: CGPoint) {
    let ev = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: pt, mouseButton: .left)
    ev?.post(tap: .cghidEventTap)
    Thread.sleep(forTimeInterval: 0.25)
}

func leftUp(at pt: CGPoint) {
    let ev = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: pt, mouseButton: .left)
    ev?.post(tap: .cghidEventTap)
    Thread.sleep(forTimeInterval: 0.25)
}

func setOptionKeyDown(_ down: Bool) {
    let flags: CGEventFlags = down ? .maskAlternate : []
    let ev = CGEvent(source: nil)
    ev?.flags = flags
    ev?.post(tap: .cghidEventTap)
    Thread.sleep(forTimeInterval: 0.25)
}

// Create a test window with standard traffic lights
func runCaptures() {
    print("Starting traffic light capture sequence...")

    for isDark in [false, true] {
        let mode = isDark ? "dark" : "light"
        setDarkMode(isDark)

        let windowRect = NSRect(x: 200, y: 200, width: 450, height: 300)
        let styleMask: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable]
        let window = NSWindow(contentRect: windowRect, styleMask: styleMask, backing: .buffered, defer: false)
        window.title = "Traffic Light Calibration - \(mode.capitalized)"
        window.appearance = NSAppearance(named: isDark ? .darkAqua : .aqua)
        window.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        Thread.sleep(forTimeInterval: 1.0)

        guard let closeBtn = window.standardWindowButton(.closeButton),
              let minBtn = window.standardWindowButton(.miniaturizeButton),
              let zoomBtn = window.standardWindowButton(.zoomButton) else {
            print("Could not obtain standard window buttons")
            continue
        }

        // Window frame coordinates on screen (AppKit bottom-left to CG top-left conversion)
        guard let screen = window.screen else { continue }
        let screenHeight = screen.frame.height
        
        let winFrame = window.frame
        let closeScreenPt = window.convertToScreen(closeBtn.frame).origin
        let minScreenPt = window.convertToScreen(minBtn.frame).origin
        let zoomScreenPt = window.convertToScreen(zoomBtn.frame).origin

        // Convert to CoreGraphics coordinates (y starts from top)
        let cgClose = CGPoint(x: closeScreenPt.x + closeBtn.frame.width / 2.0, y: screenHeight - (closeScreenPt.y + closeBtn.frame.height / 2.0))
        let cgMin = CGPoint(x: minScreenPt.x + minBtn.frame.width / 2.0, y: screenHeight - (minScreenPt.y + minBtn.frame.height / 2.0))
        let cgZoom = CGPoint(x: zoomScreenPt.x + zoomBtn.frame.width / 2.0, y: screenHeight - (zoomScreenPt.y + zoomBtn.frame.height / 2.0))

        // Region enclosing all 3 buttons
        let clusterRect = CGRect(
            x: closeScreenPt.x - 10,
            y: screenHeight - (closeScreenPt.y + closeBtn.frame.height + 12),
            width: (zoomScreenPt.x + zoomBtn.frame.width - closeScreenPt.x) + 20,
            height: closeBtn.frame.height + 24
        )

        // 1. Idle state (move mouse far away)
        moveMouse(to: CGPoint(x: 10, y: 10))
        Thread.sleep(forTimeInterval: 0.5)
        captureRect(clusterRect, filename: "\(mode)_cluster_idle.png")

        // 2. Hover states (hover close, hover min, hover zoom)
        moveMouse(to: cgClose)
        captureRect(clusterRect, filename: "\(mode)_cluster_hover_close.png")

        moveMouse(to: cgMin)
        captureRect(clusterRect, filename: "\(mode)_cluster_hover_min.png")

        moveMouse(to: cgZoom)
        captureRect(clusterRect, filename: "\(mode)_cluster_hover_zoom.png")

        // 3. Option key (Restore / Plus / Exit-Full-Screen glyph state)
        setOptionKeyDown(true)
        moveMouse(to: cgZoom)
        captureRect(clusterRect, filename: "\(mode)_cluster_hover_zoom_option.png")
        setOptionKeyDown(false)

        // 4. Pressed states (click and hold)
        moveMouse(to: cgClose)
        leftDown(at: cgClose)
        captureRect(clusterRect, filename: "\(mode)_cluster_pressed_close.png")
        leftUp(at: cgClose)

        moveMouse(to: cgMin)
        leftDown(at: cgMin)
        captureRect(clusterRect, filename: "\(mode)_cluster_pressed_min.png")
        leftUp(at: cgMin)

        moveMouse(to: cgZoom)
        leftDown(at: cgZoom)
        captureRect(clusterRect, filename: "\(mode)_cluster_pressed_zoom.png")
        leftUp(at: cgZoom)

        // 5. Inactive / Unfocused state
        // Create a second window and focus it
        let secondWindow = NSWindow(contentRect: NSRect(x: 700, y: 200, width: 300, height: 200), styleMask: [.titled], backing: .buffered, defer: false)
        secondWindow.makeKeyAndOrderFront(nil)
        moveMouse(to: CGPoint(x: 750, y: screenHeight - 250))
        Thread.sleep(forTimeInterval: 0.5)
        captureRect(clusterRect, filename: "\(mode)_cluster_inactive.png")

        secondWindow.orderOut(nil)
        window.orderOut(nil)
    }

    print("Capture sequence completed successfully.")
}

runCaptures()
