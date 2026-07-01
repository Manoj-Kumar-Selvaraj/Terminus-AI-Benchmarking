export class MessageFailure extends Error {
  constructor(reason, { exposeClassification = false } = {}) {
    super(reason);
    this.name = "MessageFailure";
    this.reason = reason;
    this.exposeClassification = exposeClassification;
  }
}
