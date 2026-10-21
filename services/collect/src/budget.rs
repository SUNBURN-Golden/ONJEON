use std::sync::Arc;

use crate::store::StoreError;

#[derive(Clone, Copy)]
pub enum Role {
    Archive,
    Ledger,
}

pub struct Session {
    meter: Arc<Meter>,
}

impl Session {
    pub fn meter(&self) -> Arc<Meter> {
        Arc::clone(&self.meter)
    }
}

pub struct Meter {
    _sealed: (),
}

impl Meter {
    pub fn check_call(
        &self,
        _op: &str,
        _role: Role,
        _bucket: &str,
        _key: Option<&str>,
        _body: Option<&[u8]>,
    ) -> Result<(), StoreError> {
        Err(StoreError::remote("remote_budget_unsupported"))
    }

    pub fn on_send(&self, _bytes: u64) -> Result<(), StoreError> {
        Err(StoreError::remote("remote_budget_unsupported"))
    }

    pub fn charge_get_bytes(&self, _bytes: u64) -> Result<(), StoreError> {
        Err(StoreError::remote("remote_budget_unsupported"))
    }
}
