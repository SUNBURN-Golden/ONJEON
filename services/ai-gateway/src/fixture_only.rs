//! Scripted provider for tests. origin=fixture: never wired into product paths.

use crate::{Provider, ProviderError, ProviderReply};
use std::sync::Mutex;

pub struct ScriptedProvider {
    label: String,
    replies: Mutex<Vec<Result<ProviderReply, ProviderError>>>,
}

impl ScriptedProvider {
    /// Replies are consumed in order; when exhausted the call fails.
    pub fn new(label: &str, replies: Vec<Result<ProviderReply, ProviderError>>) -> Self {
        let mut replies = replies;
        replies.reverse();
        Self {
            label: label.to_string(),
            replies: Mutex::new(replies),
        }
    }

    pub fn reply(text: &str, cost: u64) -> Result<ProviderReply, ProviderError> {
        Ok(ProviderReply {
            text: text.to_string(),
            model_ref: "fixture-model-ref".into(),
            cost_micro_units: cost,
        })
    }
}

impl Provider for ScriptedProvider {
    fn family_label(&self) -> &str {
        &self.label
    }
    fn complete(&self, _prompt: &str) -> Result<ProviderReply, ProviderError> {
        self.replies
            .lock()
            .unwrap()
            .pop()
            .unwrap_or(Err(ProviderError { retryable: false }))
    }
}
