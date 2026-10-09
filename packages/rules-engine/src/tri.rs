use serde::Serialize;

/// Kleene three-valued logic.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Tri {
    True,
    False,
    Unknown,
}

impl std::ops::Not for Tri {
    type Output = Tri;

    fn not(self) -> Tri {
        match self {
            Tri::True => Tri::False,
            Tri::False => Tri::True,
            Tri::Unknown => Tri::Unknown,
        }
    }
}

impl Tri {
    pub fn and(self, other: Tri) -> Tri {
        match (self, other) {
            (Tri::False, _) | (_, Tri::False) => Tri::False,
            (Tri::True, Tri::True) => Tri::True,
            _ => Tri::Unknown,
        }
    }

    pub fn or(self, other: Tri) -> Tri {
        match (self, other) {
            (Tri::True, _) | (_, Tri::True) => Tri::True,
            (Tri::False, Tri::False) => Tri::False,
            _ => Tri::Unknown,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::Tri::{self, *};

    #[test]
    fn truth_table_matches_spec_49_3() {
        let all = [True, False, Unknown];
        let and_expected = [
            (True, True, True),
            (True, False, False),
            (True, Unknown, Unknown),
            (False, False, False),
            (False, Unknown, False),
            (Unknown, Unknown, Unknown),
        ];
        let or_expected = [
            (True, True, True),
            (True, False, True),
            (True, Unknown, True),
            (False, False, False),
            (False, Unknown, Unknown),
            (Unknown, Unknown, Unknown),
        ];
        for (a, b, r) in and_expected {
            assert_eq!(a.and(b), r);
            assert_eq!(b.and(a), r, "and must be commutative");
        }
        for (a, b, r) in or_expected {
            assert_eq!(a.or(b), r);
            assert_eq!(b.or(a), r, "or must be commutative");
        }
        for a in all {
            let expected: Tri = match a {
                True => False,
                False => True,
                Unknown => Unknown,
            };
            assert_eq!(!a, expected);
        }
    }
}
