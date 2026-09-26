// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "LimitWaechter",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "LimitWaechter", path: "Sources/LimitWaechter")
    ]
)
