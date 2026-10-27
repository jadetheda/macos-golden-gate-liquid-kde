import Cocoa
import CoreGraphics
import Foundation
import ObjectiveC.runtime

dlopen("/System/Library/PrivateFrameworks/CoreUI.framework/CoreUI", RTLD_LAZY)

func dumpClassMethods(_ className: String) {
    guard let cls = NSClassFromString(className) else {
        print("Class not found: \(className)")
        return
    }
    var count: UInt32 = 0
    if let methods = class_copyMethodList(cls, &count) {
        var names: [String] = []
        for i in 0..<Int(count) {
            names.append(NSStringFromSelector(method_getName(methods[i])))
        }
        free(methods)
        print("[\(className) methods]: \(names.sorted().joined(separator: ", "))")
    }
}

dumpClassMethods("CUICatalog")
dumpClassMethods("CUIStructuredThemeStore")
dumpClassMethods("CUIThemeRendition")
dumpClassMethods("CUINamedLookup")
dumpClassMethods("CUINamedImage")
dumpClassMethods("CUINamedVectorImage")

let args = CommandLine.arguments
guard args.count >= 3 else {
    print("Usage: extract_car <path_to.car> <output_dir> [catalog.json]")
    exit(0)
}

let carPath = args[1]
let outDir = URL(fileURLWithPath: args[2])
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

func saveCGImg(_ cgImage: CGImage, to url: URL) {
    let rep = NSBitmapImageRep(cgImage: cgImage)
    if let data = rep.representation(using: .png, properties: [:]) {
        try? data.write(to: url)
    }
}

guard let catalogCls = NSClassFromString("CUICatalog") as? NSObject.Type else {
    print("No CUICatalog class")
    exit(0)
}

let allocSel = NSSelectorFromString("alloc")
let initURLSel = NSSelectorFromString("initWithURL:error:")

let allocated = catalogCls.perform(allocSel).takeUnretainedValue() as! NSObject
var err: NSError? = nil
typealias InitURLFn = @convention(c) (AnyObject, Selector, NSURL, UnsafeMutablePointer<NSError?>?) -> AnyObject?
let initImpl = allocated.method(for: initURLSel)
let initFn = unsafeBitCast(initImpl, to: InitURLFn.self)

guard let catalog = initFn(allocated, initURLSel, NSURL(fileURLWithPath: carPath), &err) as? NSObject else {
    print("Failed to open CUICatalog at \(carPath): \(String(describing: err))")
    exit(0)
}

var candidateNames = Set<String>()
let allNamesSel = NSSelectorFromString("allImageNames")
if catalog.responds(to: allNamesSel),
   let names = catalog.perform(allNamesSel)?.takeUnretainedValue() as? [String] {
    for n in names { candidateNames.insert(n) }
}

if args.count >= 4,
   let jsonData = try? Data(contentsOf: URL(fileURLWithPath: args[3])),
   let jsonArr = try? JSONSerialization.jsonObject(with: jsonData) as? [[String: Any]] {
    for item in jsonArr {
        if let n = item["Name"] as? String { candidateNames.insert(n) }
        if let rn = item["RenditionName"] as? String { candidateNames.insert(rn) }
    }
}

print("Inspecting \(candidateNames.count) candidate asset names in \(carPath)...")

let imagesWithNameSel = NSSelectorFromString("imagesWithName:")
let imageSel = NSSelectorFromString("image")
let unslicedImageSel = NSSelectorFromString("unslicedImage")
let renditionSel = NSSelectorFromString("_rendition")
let scaleSel = NSSelectorFromString("scale")
let nameSel = NSSelectorFromString("name")
let pdfDocSel = NSSelectorFromString("pdfDocument")
let createPDFImgSel = NSSelectorFromString("createImageFromPDFRenditionWithScale:")

var extractedCount = 0

for name in candidateNames.sorted() {
    let lower = name.lowercased()
    let isRelevant = lower.contains("close") || lower.contains("mini") || lower.contains("zoom") ||
                     lower.contains("window") || lower.contains("stoplight") || lower.contains("widget") ||
                     lower.contains("button") || lower.contains("titlebar") || lower.contains("traffic") ||
                     lower.contains("collapse") || lower.contains("fullscreen") || lower.contains("plus") ||
                     lower.contains("minus") || lower.contains("glass") || lower.contains("solarium")
    if !isRelevant && candidateNames.count > 150 { continue }

    guard catalog.responds(to: imagesWithNameSel),
          let lookups = catalog.perform(imagesWithNameSel, with: name)?.takeUnretainedValue() as? [NSObject] else {
        continue
    }

    for (idx, lookup) in lookups.enumerated() {
        let safeName = name.replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: " ", with: "_")
        var scaleVal: Double = 1.0
        if lookup.responds(to: scaleSel) {
            typealias ScaleFn = @convention(c) (AnyObject, Selector) -> Double
            let fn = unsafeBitCast(lookup.method(for: scaleSel), to: ScaleFn.self)
            scaleVal = fn(lookup, scaleSel)
        }

        if lookup.responds(to: imageSel) {
            typealias ImgFn = @convention(c) (AnyObject, Selector) -> Unmanaged<CGImage>?
            let fn = unsafeBitCast(lookup.method(for: imageSel), to: ImgFn.self)
            if let cgImg = fn(lookup, imageSel)?.takeUnretainedValue() {
                let outURL = outDir.appendingPathComponent("\(safeName)_\(idx)_@\(Int(scaleVal))x.png")
                saveCGImg(cgImg, to: outURL)
                extractedCount += 1
            }
        }

        if lookup.responds(to: renditionSel),
           let rend = lookup.perform(renditionSel)?.takeUnretainedValue() as? NSObject {
            if rend.responds(to: unslicedImageSel) {
                typealias ImgFn = @convention(c) (AnyObject, Selector) -> Unmanaged<CGImage>?
                let fn = unsafeBitCast(rend.method(for: unslicedImageSel), to: ImgFn.self)
                if let cgImg = fn(rend, unslicedImageSel)?.takeUnretainedValue() {
                    let outURL = outDir.appendingPathComponent("\(safeName)_\(idx)_unsliced_@\(Int(scaleVal))x.png")
                    saveCGImg(cgImg, to: outURL)
                    extractedCount += 1
                }
            }
            if rend.responds(to: createPDFImgSel) {
                typealias PDFImgFn = @convention(c) (AnyObject, Selector, Double) -> Unmanaged<CGImage>?
                let fn = unsafeBitCast(rend.method(for: createPDFImgSel), to: PDFImgFn.self)
                if let cgImg = fn(rend, createPDFImgSel, 4.0)?.takeRetainedValue() {
                    let outURL = outDir.appendingPathComponent("\(safeName)_\(idx)_pdf_@4x.png")
                    saveCGImg(cgImg, to: outURL)
                    extractedCount += 1
                }
            }
        }
    }
}

print("Extracted \(extractedCount) images from \(carPath)")
