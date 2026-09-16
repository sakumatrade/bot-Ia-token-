// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "BrokerSakuma",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "BrokerSakuma",
            path: "Sources/BrokerSakuma"
        ),
        .testTarget(
            name: "BrokerSakumaTests",
            dependencies: ["BrokerSakuma"],
            path: "Tests/BrokerSakumaTests"
        ),
    ]
)
