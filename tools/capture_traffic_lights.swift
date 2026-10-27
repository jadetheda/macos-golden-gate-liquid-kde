import Cocoa
import CoreGraphics
import Foundation
import ObjectiveC.runtime

let app = NSApplication.shared
app.setActivationPolicy(.regular)

let outputDir = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "./traffic_captures")
try? FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)

var logLines: [String] = []
func log(_ msg: String) {
    print(msg)
    logLines.append(msg)
}

let osVer = ProcessInfo.processInfo.operatingSystemVersion
log("macOS Version: \(osVer.majorVersion).\(osVer.minorVersion).\(osVer.patchVersion)")
log("Main Bundle ID: \(Bundle.main.bundleIdentifier ?? "nil")")
log("Main Bundle InfoDictionary: \(Bundle.main.infoDictionary ?? [:])")

func pumpRunLoop(_ duration: TimeInterval) {
    let deadline = Date(timeIntervalSinceNow: duration)
    while Date() < deadline {
        while let event = NSApp.nextEvent(matching: .any, until: nil, inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
        RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.015))
    }
}

func dumpObjCInfo(_ obj: AnyObject, label: String) {
    let cls: AnyClass = object_getClass(obj)!
    log("=== Introspection: \(label) (class: \(NSStringFromClass(cls))) ===")
    var currentCls: AnyClass? = cls
    while let c = currentCls {
        let cname = NSStringFromClass(c)
        if cname == "NSResponder" || cname == "NSObject" { break }
        var mCount: UInt32 = 0
        if let methods = class_copyMethodList(c, &mCount) {
            var mNames: [String] = []
            for i in 0..<Int(mCount) {
                let sel = method_getName(methods[i])
                mNames.append(NSStringFromSelector(sel))
            }
            free(methods)
            log("  [\(cname) methods]: \(mNames.sorted().joined(separator: ", "))")
        }
        var iCount: UInt32 = 0
        if let ivars = class_copyIvarList(c, &iCount) {
            var iNames: [String] = []
            for i in 0..<Int(iCount) {
                if let name = ivar_getName(ivars[i]) {
                    iNames.append(String(cString: name))
                }
            }
            free(ivars)
            log("  [\(cname) ivars]: \(iNames.sorted().joined(separator: ", "))")
        }
        currentCls = class_getSuperclass(c)
    }
}

func dumpViewHierarchy(_ view: NSView, indent: String = "") {
    let clsName = NSStringFromClass(type(of: view))
    let layerInfo = view.layer.map { "\(NSStringFromClass(type(of: $0))) frame=\($0.frame) sublayers=\($0.sublayers?.count ?? 0)" } ?? "no-layer"
    log("\(indent)- \(clsName) frame=\(view.frame) bounds=\(view.bounds) flipped=\(view.isFlipped) trackingAreas=\(view.trackingAreas.count) layer=[\(layerInfo)]")
    if let layer = view.layer {
        dumpLayerHierarchy(layer, indent: indent + "    [L] ")
    }
    for sub in view.subviews {
        dumpViewHierarchy(sub, indent: indent + "  ")
    }
}

func dumpLayerHierarchy(_ layer: CALayer, indent: String) {
    let clsName = NSStringFromClass(type(of: layer))
    log("\(indent)\(clsName) frame=\(layer.frame) opacity=\(layer.opacity) contents=\(String(describing: layer.contents)) filters=\(String(describing: layer.filters))")
    for sub in layer.sublayers ?? [] {
        dumpLayerHierarchy(sub, indent: indent + "  ")
    }
}

func savePNG(_ rep: NSBitmapImageRep, to filename: String) {
    let url = outputDir.appendingPathComponent(filename)
    if let data = rep.representation(using: .png, properties: [:]) {
        try? data.write(to: url)
        log("Saved \(filename) (\(rep.pixelsWide)x\(rep.pixelsHigh))")
    }
}

func saveCGImage(_ cgImage: CGImage, to filename: String) {
    let rep = NSBitmapImageRep(cgImage: cgImage)
    savePNG(rep, to: filename)
}

func captureWindowViaScreencapture(_ window: NSWindow, prefix: String) {
    let fullURL = outputDir.appendingPathComponent("\(prefix)_window.png")
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    proc.arguments = ["-x", "-o", "-l", "\(window.windowNumber)", fullURL.path]
    try? proc.run()
    proc.waitUntilExit()

    if let data = try? Data(contentsOf: fullURL),
       let rep = NSBitmapImageRep(data: data),
       let cgImg = rep.cgImage {
        let scale = CGFloat(cgImg.width) / window.frame.width
        let cropRect = CGRect(x: 0, y: 0, width: min(CGFloat(cgImg.width), 115.0 * scale), height: min(CGFloat(cgImg.height), 48.0 * scale))
        if let cropped = cgImg.cropping(to: cropRect) {
            saveCGImage(cropped, to: "\(prefix)_cluster_screencap.png")
        }
    }
}

func renderViewHiDPI(_ view: NSView, rect: NSRect, scale: Int, filename: String) {
    let pw = max(1, Int(rect.width) * scale)
    let ph = max(1, Int(rect.height) * scale)
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: pw,
        pixelsHigh: ph,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else { return }
    rep.size = rect.size
    view.cacheDisplay(in: rect, to: rep)
    savePNG(rep, to: filename)
}

func triggerMouseHover(on views: [NSView], in window: NSWindow, entered: Bool) {
    let loc = NSPoint(x: 20, y: window.frame.height - 18)
    let evType: NSEvent.EventType = entered ? .mouseEntered : .mouseExited
    for v in views {
        for ta in v.trackingAreas {
            if let owner = ta.owner as? NSResponder {
                if let ev = NSEvent.enterExitEvent(
                    with: evType,
                    location: loc,
                    modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime,
                    windowNumber: window.windowNumber,
                    context: nil,
                    eventNumber: 0,
                    trackingNumber: 0,
                    userData: nil
                ) {
                    if entered {
                        owner.mouseEntered(with: ev)
                    } else {
                        owner.mouseExited(with: ev)
                    }
                }
            }
        }
        // Also try private rollover selectors if present
        let rolloverSel = NSSelectorFromString("setRollover:")
        if v.responds(to: rolloverSel) {
            typealias SetBoolFn = @convention(c) (AnyObject, Selector, ObjCBool) -> Void
            let impl = v.method(for: rolloverSel)
            let fn = unsafeBitCast(impl, to: SetBoolFn.self)
            fn(v, rolloverSel, ObjCBool(entered))
        }
        if let btn = v as? NSButton, let cell = btn.cell {
            if cell.responds(to: rolloverSel) {
                typealias SetBoolFn = @convention(c) (AnyObject, Selector, ObjCBool) -> Void
                let impl = cell.method(for: rolloverSel)
                let fn = unsafeBitCast(impl, to: SetBoolFn.self)
                fn(cell, rolloverSel, ObjCBool(entered))
            }
            let mouseInGroupSel = NSSelectorFromString("_setMouseTrackingInRect:ofView:")
            _ = mouseInGroupSel
        }
        v.needsDisplay = true
    }
    window.displayIfNeeded()
    pumpRunLoop(0.25)
}

func setDarkModeSystem(_ dark: Bool) {
    // Set appearance directly in-process via NSApp.appearance and window.appearance
    // to avoid triggering a blocking TCC Automation modal prompt for System Events.
    NSApp.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
    pumpRunLoop(0.2)
}

func runAllCaptures() {
    var didIntrospect = false

    for isDark in [false, true] {
        let mode = isDark ? "dark" : "light"
        setDarkModeSystem(isDark)
        let appAppearance = NSAppearance(named: isDark ? .darkAqua : .aqua)
        NSApp.appearance = appAppearance

        let windowRect = NSRect(x: 180, y: 220, width: 460, height: 300)
        let styleMask: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable]
        let window = NSWindow(contentRect: windowRect, styleMask: styleMask, backing: .buffered, defer: false)
        window.title = "Golden Gate Traffic Calibration (\(mode))"
        window.appearance = appAppearance
        window.backgroundColor = isDark ? NSColor(srgbRed: 0.12, green: 0.12, blue: 0.13, alpha: 1.0) : NSColor(srgbRed: 0.96, green: 0.96, blue: 0.97, alpha: 1.0)

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        pumpRunLoop(1.0)

        log("[\(mode)] window.isKeyWindow=\(window.isKeyWindow) isMainWindow=\(window.isMainWindow) backingScaleFactor=\(window.backingScaleFactor)")

        guard let closeBtn = window.standardWindowButton(.closeButton),
              let minBtn = window.standardWindowButton(.miniaturizeButton),
              let zoomBtn = window.standardWindowButton(.zoomButton),
              let titlebarView = closeBtn.superview else {
            log("ERROR: Could not find standardWindowButtons")
            continue
        }

        let themeFrame = titlebarView.superview ?? titlebarView
        var allTitlebarViews: [NSView] = [closeBtn, minBtn, zoomBtn, titlebarView, themeFrame]
        for sub in titlebarView.subviews {
            if !allTitlebarViews.contains(sub) { allTitlebarViews.append(sub) }
        }

        if !didIntrospect {
            didIntrospect = true
            dumpObjCInfo(closeBtn, label: "closeBtn")
            if let cell = closeBtn.cell {
                dumpObjCInfo(cell, label: "closeBtn.cell")
            }
            dumpObjCInfo(zoomBtn, label: "zoomBtn")
            dumpObjCInfo(titlebarView, label: "titlebarView (closeBtn.superview)")
            dumpObjCInfo(themeFrame, label: "themeFrame")
            log("=== Titlebar View Hierarchy ===")
            dumpViewHierarchy(themeFrame)
        }

        // Compute bounding rect of the 3 buttons inside titlebarView
        let cRect = closeBtn.frame
        let zRect = zoomBtn.frame
        let groupRectInTitlebar = NSRect(
            x: max(0, min(cRect.minX, zRect.minX) - 8),
            y: max(0, min(cRect.minY, zRect.minY) - 6),
            width: (max(cRect.maxX, zRect.maxX) - min(cRect.minX, zRect.minX)) + 16,
            height: max(cRect.height, zRect.height) + 12
        )

        func captureState(_ stateName: String) {
            window.displayIfNeeded()
            titlebarView.displayIfNeeded()
            pumpRunLoop(0.2)
            let prefix = "\(mode)_\(stateName)"
            captureWindowViaScreencapture(window, prefix: prefix)
            renderViewHiDPI(titlebarView, rect: groupRectInTitlebar, scale: 2, filename: "\(prefix)_2x.png")
            renderViewHiDPI(titlebarView, rect: groupRectInTitlebar, scale: 4, filename: "\(prefix)_4x.png")
            renderViewHiDPI(closeBtn, rect: closeBtn.bounds, scale: 4, filename: "\(prefix)_close_4x.png")
            renderViewHiDPI(minBtn, rect: minBtn.bounds, scale: 4, filename: "\(prefix)_min_4x.png")
            renderViewHiDPI(zoomBtn, rect: zoomBtn.bounds, scale: 4, filename: "\(prefix)_zoom_4x.png")
        }

        // 1. Active Idle
        triggerMouseHover(on: allTitlebarViews, in: window, entered: false)
        captureState("01_idle")

        // 2. Active Group Hover
        triggerMouseHover(on: allTitlebarViews, in: window, entered: true)
        captureState("02_hover")

        // 3. Active Pressed Close
        closeBtn.isHighlighted = true
        captureState("03_pressed_close")
        closeBtn.isHighlighted = false

        // 4. Active Pressed Minimize
        minBtn.isHighlighted = true
        captureState("04_pressed_min")
        minBtn.isHighlighted = false

        // 5. Active Pressed Zoom
        zoomBtn.isHighlighted = true
        captureState("05_pressed_zoom")
        zoomBtn.isHighlighted = false

        // 6. Active Disabled / Deactivated
        triggerMouseHover(on: allTitlebarViews, in: window, entered: false)
        closeBtn.isEnabled = false
        minBtn.isEnabled = false
        zoomBtn.isEnabled = false
        captureState("06_disabled")
        closeBtn.isEnabled = true
        minBtn.isEnabled = true
        zoomBtn.isEnabled = true

        // 7. Inactive / Unfocused Window
        let secondWindow = NSWindow(
            contentRect: NSRect(x: 680, y: 220, width: 300, height: 200),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        secondWindow.title = "Focus Stealer"
        secondWindow.makeKeyAndOrderFront(nil)
        pumpRunLoop(0.6)
        log("[\(mode)] After focus steal: window.isKeyWindow=\(window.isKeyWindow)")

        triggerMouseHover(on: allTitlebarViews, in: window, entered: false)
        captureState("07_inactive_idle")

        // 8. Inactive Hover
        triggerMouseHover(on: allTitlebarViews, in: window, entered: true)
        captureState("08_inactive_hover")

        // 9. Inactive Pressed Close
        closeBtn.isHighlighted = true
        captureState("09_inactive_pressed_close")
        closeBtn.isHighlighted = false

        triggerMouseHover(on: allTitlebarViews, in: window, entered: false)
        secondWindow.orderOut(nil)
        window.orderOut(nil)
        pumpRunLoop(0.3)
    }

    let reportURL = outputDir.appendingPathComponent("runtime_introspection.txt")
    try? logLines.joined(separator: "\n").write(to: reportURL, atomically: true, encoding: .utf8)
    log("All captures and introspection saved.")
}

runAllCaptures()
