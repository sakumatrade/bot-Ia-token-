import XCTest
@testable import BrokerSakuma

final class BeginnerErrorTests: XCTestCase {
    func testServerErrorNeverExposesRawStatusCodeInHeadline() {
        let presentation = BeginnerMessage.present(APIError.serverError(statusCode: 500))
        XCTAssertFalse(presentation.headline.contains("500"))
        XCTAssertTrue(presentation.technicalDetails.contains("500"))
    }

    func testNotConnectedHasAPortugueseBeginnerHeadline() {
        let presentation = BeginnerMessage.present(APIError.notConnected)
        XCTAssertFalse(presentation.headline.isEmpty)
        XCTAssertFalse(presentation.headline.contains("Error"))
    }

    func testEachAPIErrorCaseHasADistinctHeadline() {
        let errors: [APIError] = [
            .notConnected, .serverError(statusCode: 500), .decodingFailed, .unauthorized, .missingAPIKey,
        ]
        let headlines = Set(errors.map { BeginnerMessage.present($0).headline })
        XCTAssertEqual(headlines.count, errors.count, "each error case should have its own explanation")
    }

    func testMissingAPIKeyPointsToSettings() {
        let presentation = BeginnerMessage.present(APIError.missingAPIKey)
        XCTAssertTrue(presentation.headline.contains("Configurações"))
    }
}
