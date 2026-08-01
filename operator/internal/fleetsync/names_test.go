package fleetsync

import "testing"

func TestResourceNameUsesOwnerRepo(t *testing.T) {
	got := ResourceName("https://github.com/acme/tf-vpc.git")
	if got != "acme-tf-vpc" {
		t.Fatalf("ResourceName() = %q, want acme-tf-vpc", got)
	}
}

func TestResourceNameDistinctOwners(t *testing.T) {
	a := ResourceName("https://github.com/acme/vpc")
	b := ResourceName("https://github.com/other/vpc")
	if a == b {
		t.Fatalf("expected distinct names, both %q", a)
	}
}
